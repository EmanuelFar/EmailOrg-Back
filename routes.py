import base64
import json

import googleapiclient.discovery
import google.oauth2.credentials

from pymongo import MongoClient

from fastapi import FastAPI, HTTPException

from app.config import API_SERVICE_NAME, API_VERSION, MONGODB_URI
from app.email_services import *
from app.models import WebhookData, LabelUpdate, LabelingRequest, PastEmailSort, BulkRemove

# Initialize the FastAPI app
app = FastAPI()

# Initialize the MongoDB client and get the collections
client = MongoClient(MONGODB_URI)
db = client.get_database("your_database_name")
db_users = db.get_collection("users")
db_accounts = db.get_collection("accounts")


@app.post('/bulk_remove_mails')
async def bulk_remove_mails(request_data: BulkRemove):
    user_email = request_data.user_email
    sender_email = request_data.sender_email
    try:
        await delete_emails_by_sender(user_email, sender_email)
    except Exception as e:
        print(e)
        return
    return "Delete Ended Successfully!"


@app.delete('/delete_account')
async def delete_account(email: str):
    try:
        account = db_users.find_one({"email": email})
        if account:
            account_id = account["_id"]
            db_users.delete_one({"_id": account_id})
            db_accounts.delete_one({"userId": account_id})
            return {"message": "Account deleted successfully"}
        else:
            return {"message": "User not found"}
    except Exception as error:
        return {"error": str(error)}


@app.post('/update_labels')
async def update_labels(request_data: LabelUpdate):
    user_email = request_data.email
    user_labels = request_data.labels
    selected_labels = []
    for i in range(len(user_labels)):
        if user_labels[i]:
            selected_labels.append(labels_list[i])

    if user_email:
        result = db_users.update_one(
            {'email': user_email},
            {'$set': {'labels': selected_labels}},
            upsert=True  # Creates a new document if it doesn't exist
        )
        await create_labels(selected_labels, user_email)
        return {'message': f'Labels updated for user {user_email}'}
    else:
        raise HTTPException(status_code=400, detail='User ID not provided')


@app.post('/gmail_watch')
async def manage_gmail_watch(request_data: LabelingRequest):
    user_email = request_data.email
    action = request_data.action
    if action == 'start':
        # Logic to start Gmail API watch method
        try:
            await start_gmail_watch(user_email)
            return {"message": "Gmail watch started successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error starting Gmail watch: {e}")
    elif action == 'stop':
        try:
            await stop_gmail_watch(user_email)
            return {"message": "Gmail watch stopped successfully"}
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error stopping Gmail watch: {e}")
    else:
        raise HTTPException(status_code=400, detail="Invalid action. Use 'start' or 'stop'")


@app.post('/past_email_sorter')
async def past_email_sorter(request_data: PastEmailSort):
    labels_span = ["Alerts", "Deliveries", "Receipts", "Updates"]
    labels_list_from_request = request_data.chosen_labels

    #Finds the requested label index from Boolean list sent in request
    label_index = labels_list_from_request.index(True)
    label = labels_span[label_index]
    user_email = request_data.user_email
    sender_email = request_data.sender_email
    num_of_messages = request_data.messages_amount
    try:
        await filter_last_emails_by_sender(user_email, sender_email, label, int(num_of_messages))
    except Exception as e:
        return e
    return "Emailed Filtered Successfully!"


@app.get('/get_user_data_ai_labeling')
async def get_user_data(email: str):
    try:
        # Retrieve user data from MongoDB based on the provided email
        user_data = db_users.find_one({'email': email})
        if user_data:
            return [user_data["labels"], user_data["startLabel"]]
        else:
            raise HTTPException(status_code=404, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error user data: {e}")


@app.get('/webhook')
async def webhook():
    # Webhook example
    webhook_data = {
        "message": {"data": "eyJlW5vZmFyZXMxMjNAZ21haWwuY29tIiwiaGlzdG9ywNDAxfQ==",
                    "messageId": "993744104800", "message_id": "9937084800",
                    "publishTime": "2023-12-25T17", "publish_time": "2023-12-25T17"},
        "subscription": "projects/"}

    # takes the json_data and decode it using bash64
    decoded_data = base64.b64decode(webhook_data['message']['data']).decode('utf-8')
    json_decoded_data = json.loads(decoded_data)
    webhook_history_id = fetch_historyid_update_webhook(json_decoded_data)
    webhook_email = json_decoded_data["emailAddress"]
    await get_new_email_messages_from_watch(webhook_email, webhook_history_id)
    return {"data:" "webhook data has been sent"}
