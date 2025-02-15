import openai
from config import OPENAI_KEY

openai.api_key = OPENAI_KEY

async def gpt_call(labels: list, message_subject: str, message_content: str):
    message = {
        'role': 'user',
        'content': f'''
        You are a professional email sorter. 
        I will give you an email subject and content along with a list of labels. 
        Choose the most appropriate label from the list.
        
        Subject: {message_subject}
        Content: {message_content}
        Labels: {labels}
        '''
    }
    response = openai.ChatCompletion.create(
        model='gpt-3.5-turbo',
        messages=[message]
    )
    return response.choices[0].message['content'].strip()

async def gpt_call_filter_by_sender(label: str, message_subject: str, message_content: str):
    message = {
        'role': 'user',
        'content': f'''
        You are a professional email sorter.
        I will give you an email subject and content along with a single label. 
        Determine if the label fits the email.
        
        Subject: {message_subject}
        Content: {message_content}
        Label: {label}
        Respond with 'YES' or 'NO'.
        '''
    }
    response = openai.ChatCompletion.create(
        model='gpt-3.5-turbo',
        messages=[message]
    )
    return response.choices[0].message['content'].strip()
