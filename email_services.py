import googleapiclient.discovery
import google.oauth2.credentials
from fastapi import HTTPException

from config import *
from database import *
from openai_integration import gpt_call, gpt_call_filter_by_sender
import logging
from itertools import chain

async def create_credentials(user_email):
    user = db_users.find_one({"email": user_email})
    if user:
        user_id = user["_id"]
        account = db_accounts.find_one({"userId": user_id})
        user_access_token = account.get("access_token")
        user_refresh_token = account.get("refresh_token")

        # Credentials fetch
        try:
            credentials = google.oauth2.credentials.Credentials(
                token=user_access_token,
                refresh_token=user_refresh_token,
                token_uri=TOKEN_URI,
                client_id=CLIENT_ID,
                client_secret=CLIENT_SECRET,
                scopes=SCOPES_LIST
            )
            
            if credentials.expired and credentials.refresh_token:
                request = google.auth.transport.requests.Request()
                credentials.refresh(request)
                # Store the new access token and refresh token in the database
                db_accounts.update_one(
                    {"userId": user_id},
                    {"$set": {
                        "access_token": credentials.token,
                        "refresh_token": credentials.refresh_token  
                    }}
                )

        except Exception as error:
            logging.error(f"{user_email} {error}")
            return

        return credentials

async def manage_gmail_watch(user_email: str, start_watch: bool):
    """
    Enable/Disable Gmail Watch service using Gmail API.
    """
    credentials_doc = await create_credentials(user_email)

    if not credentials_doc:
        raise HTTPException(status_code=400, detail=f"Credentials not found for user {user_email}")

    service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)

    if start_watch:
        request_body = {'labelIds': ['INBOX'], 'topicName': TOPIC_NAME}
        service.users().watch(userId='me', body=request_body).execute()

        # Update database to indicate that the watch has started
        filter_criteria = {"email": user_email}
        update_data = {"$set": {"startLabel": "True"}}
    else:
        # Stop watching for changes
        service.users().stop(userId='me').execute()

        filter_criteria = {"email": user_email}
        update_data = {"$set": {"startLabel": "False"}}

    db_users.update_one(filter_criteria, update_data, upsert=True)


async def get_email_from_watch(webhook_email: str, webhook_history_id: str):
    """
    Processes new Gmail messages from a webhook, checks for labels, and applies labels based on the email content
    using the Gmail API and GPT. Retrieves user credentials, filters message history, and applies appropriate labels
    to new, unlabeled messages.
    """

    # Retrieve credentials from MongoDB based on the webhook email
    credentials_doc = await create_credentials(webhook_email)

    if not credentials_doc:
        raise HTTPException(status_code=400, detail=f"Credentials not found for user {webhook_email}")

    # Retrieve user info (labels and startLabel flag)
    user_info = db_users.find_one({"email": webhook_email})
    if not user_info:
        logging.error(f"User info not found for {webhook_email}")
        return

    user_labels = user_info.get("labels")
    start_label_flag = user_info.get("startLabel")

    # Check if startLabel is enabled
    if start_label_flag != "True":
        logging.warning("Please enable Gmail watch!")
        return

    # Use credentials to interact with Gmail API
    service = googleapiclient.discovery.build('gmail', 'v1', credentials=credentials_doc)

    # Fetch history from Gmail API
    try:
        response = service.users().history().list(userId='me', startHistoryId=webhook_history_id).execute()
    except Exception as e:
        logging.error(f"Error fetching history: {e}")
        return

    changes_raw = response.get('history')
    if not changes_raw:
        logging.info("No new changes")
        return

    # Filter and flatten new messages from history
    changes_filtered = [d for d in changes_raw if 'messagesAdded' in d]
    messages_added_values_filtered = list(chain.from_iterable(item['messagesAdded'] for item in changes_filtered))

    if not messages_added_values_filtered:
        logging.info("No new messages")
        return

    # Process each new message
    for message in messages_added_values_filtered:
        new_message_id = message['message']['id']

        # Check if the message is already labeled
        try:
            labels = service.users().messages().get(userId='me', id=new_message_id).execute().get('labelIds', [])
        except Exception as e:
            logging.error(f"Error checking labels for message {new_message_id}: {e}")
            continue

        if any(label.startswith('Label_') for label in labels):
            continue

        # Retrieve email details using the message ID
        try:
            email = service.users().messages().get(userId='me', id=new_message_id).execute()
        except Exception as e:
            logging.error(f"Error fetching email details for message {new_message_id}: {e}")
            continue

        # Extract subject using next() for better readability
        subject = next((header['value'] for header in email['payload']['headers'] if header['name'] == 'Subject'), None)
        if not subject:
            logging.warning(f"Subject not found for message {new_message_id}")
            continue

        logging.info(f"Subject: {subject}\nEmail Content: {email['snippet']}")

        # Call function to determine label and apply it to the message
        label = await gpt_call(user_labels, subject, email['snippet'])
        await label_message(new_message_id, label, credentials_doc)


async def create_labels(user_chosen_labels: list, user_email: str):
    """
      Creates user-specific labels in Gmail if they don't already exist.
      Uses the Gmail API to create new labels based on user preferences and associated label colors.
      """
    credentials_doc = await create_credentials(user_email)

    if not credentials_doc:
        raise HTTPException(status_code=400, detail=f"Credentials not found for user {user_email}")

    # Build connection with Gmail API
    drive = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)

    # Get current user labels from Gmail account
    current_user_labels = drive.users().labels().list(userId='me').execute().get('labels', [])

    # Extract names of existing labels for comparison
    filtered_current_user_labels = [label['name'] for label in current_user_labels]

    # Loop through user-chosen labels to create new ones if they don't exist
    for label in user_chosen_labels:
        if not label in filtered_current_user_labels:
            # Create new label with specified properties if it doesn't exist
            label_body = label_color_dict[label]
            drive.users().labels().create(userId='me', body=label_body).execute()


async def label_message(message_id: str, label: str, credentials: object):
    """
    Applies a message to a label.
    """
    service = googleapiclient.discovery.build('gmail', 'v1', credentials=credentials)

    # Get all labels
    response = service.users().labels().list(userId='me').execute()
    user_labels = response.get('labels', [])

    label_id = None
    # Find the label ID based on the label name
    for label in user_labels:
        if label['name'] == label:
            label_id = label['id']
            break

    if label_id:
        # Modify the message to add the label
        label_body = {'addLabelIds': [label_id], 'removeLabelIds': []}
        modified_message = service.users().messages().modify(userId='me', id=message_id, body=label_body).execute()
        print(f"Added label '{label}' to message ID: {message_id}")
        return modified_message
    else:
        print(f"Label '{label}' not found.")


async def get_create_label(service, user_id, label_name, parent_label_name=None):
    """
    Checks if a label exists, if not, creates it. Returns the label ID.
    """
    labels = service.users().labels().list(userId=user_id).execute().get('labels', [])

    # Check if label exists
    for label in labels:
        if label['type'] == 'user' and label['name'] == label_name:
            return label['id']

    # If the label doesn't exist, create it
    new_label = {
        'messageListVisibility': 'show',
        'name': label_name,
        'labelListVisibility': 'labelShow'
    }

    # If this is a son label, format its name accordingly
    if parent_label_name:
        new_label['name'] = f"{parent_label_name}/{label_name}"

    created_label = service.users().labels().create(userId=user_id, body=new_label).execute()
    return created_label['id']


async def filter_emails_by_sender(user_email: str, sender_email: str, label_chosen: str, num_of_messages: int):
    """
    Given a specific sender Email Address, label last @num_of_messages
    amount of last Emails sent by the sender.
    """
    # Define email addresses, label, and retrieve user credentials
    sender_name = sender_email.split('@')[0]
    credentials_doc = await create_credentials(user_email)

    if not credentials_doc:
        raise HTTPException(status_code=400, detail=f"Credentials not found for user {user_email}")

    service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)

    # Get IDs of the last X emails from the sender
    results = service.users().messages().list(userId='me', q=f'from:{sender_email}',
                                              maxResults=num_of_messages).execute()
    messages = results.get('messages', [])

    parent_label_id = await get_create_label(service, 'me', sender_name)

    son_label_name = f"{sender_name}/{label_chosen}"
    son_label_id = await get_create_label(service, 'me', son_label_name)

    # Loop through the messages from the sender
    for message in messages:
        email_id = message['id']
        msg = service.users().messages().get(userId='me', id=email_id).execute()

        # If the message is already labeled, skip
        msg_labels_list = msg.get('labelIds', [])
        if son_label_id in msg_labels_list:
            print("Already labeled!")
            continue

        # Extract email subject
        for header in msg['payload']['headers']:
            if header['name'] == 'Subject':
                subject = header['value']
                break

        # Check if subject exists and print email content
        if 'subject' in locals():
            # Call function to determine label and apply it to the message
            if await gpt_call_filter_by_sender(label_chosen, subject, msg['snippet']) == 'Yes':
                service.users().messages().modify(userId='me', id=email_id,
                                                  body={'addLabelIds': [son_label_id]}).execute()
        else:
            print('Subject not found')


async def fetch_historyId_update_webhook(data):
    """
    checks for the user email inside @data, if user in database -
    returns stored history id and updates to new history id.
    """
    user_email = data["emailAddress"]
    new_history_id = data["historyId"]
    filter_criteria = {"email": user_email}
    update_data = {"$set": {"historyId": new_history_id}}
    db_users.update_one(filter_criteria, update_data, upsert=True)
    return new_history_id if not db_users.find_one({"email": user_email}).get("historyId") else data["historyId"]


async def delete_emails_by_sender(user_email: str, sender_email: str):
    """
    Deletes last 500 Emails sent by a certain sender.
    """
    credentials_doc = await create_credentials(user_email)

    if not credentials_doc:
        raise HTTPException(status_code=400, detail=f"Credentials not found for user {user_email}")

    service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)
    try:
        results = service.users().messages().list(userId='me', q=f'from:{sender_email}', maxResults=500).execute()
        messages = results.get('messages', [])
        # Delete the last X emails from the sender
        if messages:
            for message in messages:
                message_id = message['id']
                service.users().messages().delete(userId='me', id=message_id).execute()

    except googleapiclient.errors.HttpError as error:
        print(f"An error occurred: {error}")
    return f"Mails from {sender_email} were deleted!"
