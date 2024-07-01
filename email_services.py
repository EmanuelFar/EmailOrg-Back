import googleapiclient.discovery
import google.oauth2.credentials
from pymongo import MongoClient
from app.config import *
from app.models import *
from fastapi import HTTPException
from app.openai_integration import gpt_call, gpt_call_filter_by_sender

client = MongoClient(MONGODB_URI)
db = client.get_database("your_database_name")
db_users = db.get_collection("users")
db_accounts = db.get_collection("accounts")

async def create_credentials(user_email):
    user = db_users.find_one({"email": user_email})
    if user:
        user_id = user["_id"]
        user_access_token = db_accounts.find_one({"userId": user_id}).get("access_token")
        user_refresh_token = db_accounts.find_one({"userId": user_id}).get("refresh_token")
        # Credentials fetch example
        try:
            credentials = google.oauth2.credentials.Credentials(
                token=user_access_token,
                refresh_token=user_refresh_token,
                token_uri='',
                client_id='',
                client_secret='',
                scopes=SCOPES_LIST
            )
        except Exception as error:
            print(error)
            return

        return credentials
    else:
        print("User not found in Database")


async def stop_gmail_watch(user_email):
    credentials_doc = await create_credentials(user_email)
    service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)

    # Stop watching for changes
    service.users().stop(userId='me').execute()
    # Change value in db
    filter_criteria = {"email": user_email}
    update_data = {"$set": {"startLabel": "False"}}
    db_users.update_one(filter_criteria, update_data, upsert=True)


async def start_gmail_watch(user_email):
    credentials_doc = await create_credentials(user_email)
    service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)
    request_body = {'labelIds': ['INBOX'], 'topicName': 'projects/emailorganizer-409013/topics/EmailOrganizer'}
    #Start watching for changes
    service.users().watch(userId='me', body=request_body).execute()
    #change value in db
    filter_criteria = {"email": user_email}
    update_data = {"$set": {"startLabel": "True"}}
    db_users.update_one(filter_criteria, update_data, upsert=True)


async def get_new_email_messages_from_watch(webhook_email, webhook_history_id):
    """
    Retrieves new email messages from Gmail history using webhook information.
    """
    # Retrieve credentials and user labels from the database
    credentials_doc = await create_credentials(webhook_email)
    user_info = db_users.find_one({"email": webhook_email})
    user_labels = user_info.get("labels")
    start_label = user_info.get("startLabel") == "True"

    # If credentials are not found or startLabel is not enabled, exit early
    if not credentials_doc:
        print("No credentials found for this email")
        return

    if not start_label:
        print("Please Enable Gmail watch!")
        return

    # Use credentials to interact with Gmail API
    service = googleapiclient.discovery.build('gmail', 'v1', credentials=credentials_doc)
    # Fetch history from Gmail API
    response = service.users().history().list(userId='me', startHistoryId=webhook_history_id).execute()
    changes_raw = response.get('history')

    if not changes_raw:
        print("No new changes")
        return

    # Filter new messages from history
    messages_added = [
        message['messagesAdded']
        for change in changes_raw
        if 'messagesAdded' in change
    ]
    
    if not messages_added:
        print("No new messages")
        return

    # Flatten the list of added messages
    messages_flat = [msg for sublist in messages_added for msg in sublist]

    # Process each new message
    for message in messages_flat:
        new_message_id = message['message']['id']
        email = service.users().messages().get(userId='me', id=new_message_id).execute()

        # Check if the message is already labeled
        if any(label.startswith('Label_') for label in email.get('labelIds', [])):
            print("Already labeled")
            continue

        # Extract subject and snippet
        subject = next((header['value'] for header in email['payload']['headers'] if header['name'] == 'Subject'), None)
        snippet = email.get('snippet')

        if subject:
            print('Subject:', subject)
            print('Email Content:', snippet)

            # Call function to determine label and apply it to the message
            label = await gpt_call(user_labels, subject, snippet)
            labelize_message(new_message_id, label, credentials_doc)
        else:
            print('Subject not found')



async def filter_last_emails_by_sender(user_email: str, sender_email: str, label_chosen: str, num_of_messages: int):
    """
    Filters the last 'num_of_messages' emails from 'sender_email' and labels them under the specified 'label_chosen'.
    """
    sender_name = sender_email.split('@')[0]
    
    # Retrieve user credentials and Gmail service
    credentials_doc = await create_credentials(user_email)
    service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)
    
    # Get IDs of the last X emails from the sender
    messages = get_last_emails_from_sender(service, sender_email, num_of_messages)
    if not messages:
        print("No messages found from the sender.")
        return
    
    # Ensure parent and child labels exist
    parent_label_id = await get_or_create_label(service, sender_name)
    son_label_name = f"{sender_name}/{label_chosen}"
    son_label_id = await get_or_create_label(service, son_label_name)

    # Process and label the messages
    for message in messages:
        await process_and_label_message(service, message, son_label_id, label_chosen)

async def get_last_emails_from_sender(service, sender_email: str, num_of_messages: int):
    results = service.users().messages().list(userId='me', q=f'from:{sender_email}', maxResults=num_of_messages).execute()
    return results.get('messages', [])

async def get_or_create_label(service, label_name: str):
    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    for label in labels:
        if label['type'] == 'user' and label['name'] == label_name:
            return label['id']
    
    new_label = {
        'messageListVisibility': 'show',
        'name': label_name,
        'labelListVisibility': 'labelShow'
    }
    created_label = service.users().labels().create(userId='me', body=new_label).execute()
    return created_label['id']

async def process_and_label_message(service, message, label_id: str, label_chosen: str):
    email_id = message['id']
    msg = service.users().messages().get(userId='me', id=email_id).execute()
    
    if label_id in msg.get('labelIds', []):
        print("Already labeled!")
        return
    
    subject = next((header['value'] for header in msg['payload']['headers'] if header['name'] == 'Subject'), None)
    snippet = msg.get('snippet')

    if subject:
        if await gpt_call_filter_by_sender(label_chosen, subject, snippet) == 'Yes':
            service.users().messages().modify(userId='me', id=email_id, body={'addLabelIds': [label_id]}).execute()
    else:
        print('Subject not found')




async def create_labels(user_chosen_labels: list, user_email: str):
    credentials_doc = await create_credentials(user_email)
    # Build connection with Gmail API
    drive = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)

    # Retrieve current user labels from Gmail account
    current_user_labels = drive.users().labels().list(userId='me').execute().get('labels', [])

    # Extract names of existing labels for comparison
    filtered_current_user_labels = [label['name'] for label in current_user_labels]

    # Loop through user-chosen labels to create new ones if they don't exist
    for label in user_chosen_labels:
        if not label in filtered_current_user_labels:
            # Create new label with specified properties if it doesn't exist
            label_body = label_color_dict[label]
            drive.users().labels().create(userId='me', body=label_body).execute()


async def labelize_message(message_id: str, label: str, credentials: object):
    service = googleapiclient.discovery.build('gmail', 'v1', credentials=credentials)

    # Get all labels
    response = service.users().labels().list(userId='me').execute()
    user_labels = response.get('labels', [])

    label_id = None
    # Find the label ID based on the label name
    for l in user_labels:
        if l['name'] == label:
            label_id = l['id']
            break

    if label_id:
        # Modify the message to add the label
        label_body = {'addLabelIds': [label_id], 'removeLabelIds': []}
        modified_message = service.users().messages().modify(userId='me', id=message_id, body=label_body).execute()
        print(f"Added label '{label}' to message ID: {message_id}")
        return modified_message
    else:
        print(f"Label '{label}' not found.")
        return None


async def delete_emails_by_sender(user_email: str, sender_email: str):
    credentials_doc = await create_credentials(user_email)
    service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)
    try:
        results = service.users().messages().list(userId='me', q=f'from:{sender_email}', maxResults=500).execute()
        messages = results.get('messages', [])
        # Delete the last X emails from the sender
        if messages:
            for message in messages:  # Delete the last 5 emails
                message_id = message['id']
                service.users().messages().delete(userId='me', id=message_id).execute()

    except googleapiclient.errors.HttpError as error:
        print(f"An error occurred: {error}")
    return f"Mails from {sender_email} were deleted!"
