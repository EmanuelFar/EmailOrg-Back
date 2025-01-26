import base64
import json

from fastapi import FastAPI

from email_services import *
from models import WebhookData, LabelUpdate, LabelingRequest, PastEmailSort, BulkRemove
from database import *

# Initialize the FastAPI app
app = FastAPI()


@app.post('/bulk_remove_mails')
async def bulk_remove_mails(request_data: BulkRemove):
    if not request_data.user_email or not request_data.sender_email:
        raise HTTPException(status_code=400, detail="User email and sender email are required")

    user_email = request_data.user_email
    sender_email = request_data.sender_email
    try:
        await delete_emails_by_sender(user_email, sender_email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to bulk delete - {e}")

    return {"message": "Delete Ended Successfully!"}


@app.delete('/delete_account')
async def delete_account(email: str):
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    try:
        account = db_users.find_one({"email": email})
        if account:
            account_id = account["_id"]
            db_users.delete_one({"_id": account_id})
            db_accounts.delete_one({"userId": account_id})
            return {"message": "Account deleted successfully"}
        else:
            raise HTTPException(status_code=500, detail="User not found")
    except Exception as error:
        raise HTTPException(status_code=500, detail=f"Error deleting account: {error}")


@app.post('/update_labels')
async def update_labels(request_data: LabelUpdate):
    if not request_data.email or not request_data.labels:
        raise HTTPException(status_code=400, detail="Email and labels are required")

    user_email = request_data.email
    user_labels = request_data.labels

    try:
        db_users.update_one(
            {'email': user_email},
            {'$set': {'labels': user_labels}},
            upsert=True  # Creates a new document if it doesn't exist
        )
        await create_labels(user_labels, user_email)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to update labels: {e}")

    return {'message': f'Labels updated for user {user_email}'}


@app.post('/gmail_watch')
async def gmail_watch(request_data: LabelingRequest):
    if not request_data.email or not request_data.action:
        raise HTTPException(status_code=400, detail="Email and action (start/stop) are required")

    user_email = request_data.email
    action = request_data.action

    if action not in ["start", "stop"]:
        raise HTTPException(status_code=400, detail="Invalid action. Allowed actions are 'start' and 'stop'.")

    try:
        send_acc = True if action == 'start' else False
        await manage_gmail_watch(user_email, send_acc)
        return {"message": f"Gmail watch {action}ed successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error {action}ing Gmail watch: {e}")


@app.post('/past_email_sorter')
async def past_email_sorter(request_data: PastEmailSort):
    if not request_data.chosen_labels or not request_data.user_email or not request_data.sender_email:
        raise HTTPException(status_code=400, detail="User email, sender email, and labels are required")

    # Limited labels
    labels_span = ["Alerts", "Deliveries", "Receipts", "Updates"]
    labels_list_from_request = request_data.chosen_labels

    # Ensure there's a valid label selection
    try:
        label_index = labels_list_from_request.index(True)
    except ValueError:
        raise HTTPException(status_code=400, detail="Valid label not selected")

    label = labels_span[label_index]
    user_email = request_data.user_email
    sender_email = request_data.sender_email
    num_of_messages = request_data.messages_amount

    try:
        await filter_emails_by_sender(user_email, sender_email, label, int(num_of_messages))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error filtering emails: {e}")

    return {"message": "Emails filtered successfully!"}


@app.get('/get_user_data_ai_labeling')
# Loads user Dashboard
async def get_user_data(email: str):
    # Ensure email is provided
    if not email:
        raise HTTPException(status_code=400, detail="Email is required")

    try:
        # Retrieve user data from MongoDB based on the provided email
        user_data = db_users.find_one({'email': email})
        if user_data:
            return [user_data["labels"], user_data["startLabel"]]
        else:
            raise HTTPException(status_code=500, detail="User not found")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error retrieving user data: {e}")


@app.get('/webhook')
async def webhook(request: WebhookData):
    # Ensure the request message is present
    if not request.message or 'data' not in request.message:
        raise HTTPException(status_code=400, detail="Invalid webhook data")

    # The webhook is a callback function that is triggered by a Pub/Sub message
    # sent by Gmail API when there is a new message or a change to the inbox.

    webhook_data = request.message
    decoded_data = base64.b64decode(webhook_data['message']['data']).decode('utf-8')

    try:
        json_decoded_data = json.loads(decoded_data)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid JSON in webhook data")

    # The historyId is used to track changes in the Gmail account (e.g., new messages)
    # and this history ID is sent by Gmail API to notify the subscriber of new changes.
    # Here, we're fetching the historyId and updating the webhook with it.
    webhook_history_id = fetch_historyId_update_webhook(json_decoded_data)

    # Extract the email address from the decoded webhook data.
    webhook_email = json_decoded_data.get("emailAddress")
    if not webhook_email:
        raise HTTPException(status_code=400, detail="Email address not found in webhook data")

    # Once we have the email and history ID, we call the get_email_from_watch function,
    # which uses the Gmail API to fetch new email data based on the provided webhook
    # history ID and email address.
    try:
        await get_email_from_watch(webhook_email, webhook_history_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching emails from watch: {e}")

    # Return a response indicating that the webhook data has been processed.
    return {"message": "Webhook data has been processed"}
