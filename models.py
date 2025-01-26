from pydantic import BaseModel
from typing import List

class WebhookData(BaseModel):
    message: dict

class LabelUpdate(BaseModel):
    labels: List[bool]
    email: str

class LabelingRequest(BaseModel):
    email: str
    action: str

class PastEmailSort(BaseModel):
    user_email: str
    sender_email: str
    chosen_labels: List[bool]
    messages_amount: str

class BulkRemove(BaseModel):
    user_email: str
    sender_email: str
