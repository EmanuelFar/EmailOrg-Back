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
    # Retrieve credentials from MongoDB based on the webhook email
    credentials_doc = await create_credentials(webhook_email)
    user_labels = db_users.find_one({"email": webhook_email}).get("labels")

    # Check for credentials and startLabel flag in the collection
    if credentials_doc:
        if db_users.find_one({"email": webhook_email}).get("startLabel") == "True":
            # Use credentials to interact with Gmail API
            service = googleapiclient.discovery.build('gmail', 'v1', credentials=credentials_doc)
            # Fetch history from Gmail API
            response = service.users().history().list(userId='me', startHistoryId=webhook_history_id).execute()
            changes_raw = response.get('history')
            if not changes_raw:
                print("no new changes")
                return

            # Filter new messages from history
            changes_filtered = [d for d in changes_raw if 'messagesAdded' in d]
            if len(changes_filtered) == 0:
                print('No new messages')
                return

            # Extract added messages and flatten the list
            messages_added_values_raw = [item['messagesAdded'] for item in changes_filtered]
            messages_added_values_filtered = []
            [messages_added_values_filtered.extend(item) for item in messages_added_values_raw]

            for message in messages_added_values_filtered:
                already_labeled = False
                print(message)
                new_message_id = message['message']['id']

                # Check if the message is already labeled
                for user_label_id in service.users().messages().get(userId='me', id=new_message_id).execute().get(
                        'labelIds'):
                    if user_label_id.startswith('Label_'):
                        already_labeled = True
                        print("Already labeled")
                        
                if not already_labeled:
                    # Retrieve email details using the message ID
                    email = service.users().messages().get(userId='me', id=new_message_id).execute()
                    for header in email['payload']['headers']:
                        if header['name'] == 'Subject':
                            subject = header['value']
                            break
                    if 'subject' in locals():
                        print('Subject:', subject)
                        print('Email Content:', email['snippet'])

                        # Call function to determine label and apply it to the message
                        label = await gpt_call(user_labels, subject, email['snippet'])
                        labelize_message(new_message_id, label, credentials_doc)
                    else:
                        print('Subject not found')
                else:
                    continue
        else:
            print("Please Enable Gmail watch!")
    else:
        print("No credentials found for this email")
    return


async def filter_last_emails_by_sender(user_email: str, sender_email: str, label_chosen: str, num_of_messages: int):
    # Define email addresses, label, and retrieve user credentials
    sender_name = sender_email.split('@')[0]
    credentials_doc = await create_credentials(user_email)
    service = googleapiclient.discovery.build(API_SERVICE_NAME, API_VERSION, credentials=credentials_doc)

    # Get IDs of the last X emails from the sender
    results = service.users().messages().list(userId='me', q=f'from:{sender_email}',
                                              maxResults=num_of_messages).execute()
    messages = results.get('messages', [])
    parent_label_id = None
    labels = service.users().labels().list(userId='me').execute().get('labels', [])
    # Check if parent label (sender's name) exists
    for label in labels:
        if label['type'] == 'user' and label['name'] == sender_name:
            parent_label_id = label['id']
            break

    # If parent label doesn't exist, create it
    if not parent_label_id:
        new_label = {'messageListVisibility': 'show', 'name': sender_name, 'labelListVisibility': 'labelShow'}
        created_label = service.users().labels().create(userId='me', body=new_label).execute()
        parent_label_id = created_label['id']

    # Define son label name and check if it exists
    son_label_name = f"{sender_name}/{label_chosen}"
    son_label_id = None

    for label in labels:
        if label['type'] == 'user' and label['name'] == son_label_name:
            son_label_id = label['id']
            break

    # If son label doesn't exist, create it
    if not son_label_id:
        son_label = {'messageListVisibility': 'show', 'name': son_label_name, 'labelListVisibility': 'labelShow'}
        son_label = service.users().labels().create(userId='me', body=son_label).execute()
        son_label_id = son_label['id']

    # Loop through the messages from the sender
    for message in messages:
        email_id = message['id']
        msg = service.users().messages().get(userId='me', id=email_id).execute()
        #If the message is already labeled, skip
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
#checks for the user email inside data, search if user in data base, return stored historyid, update to the new history
async def fetch_historyid_update_webhook(data):
    user_email = data["emailAddress"]
    new_history_id = data["historyId"]
    filter_criteria = {"email": user_email}
    update_data = {"$set": {"historyId": new_history_id}}
    db_users.update_one(filter_criteria, update_data, upsert=True)
    return new_history_id if not db_users.find_one({"email": user_email}).get("historyId") else data["historyId"]


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
