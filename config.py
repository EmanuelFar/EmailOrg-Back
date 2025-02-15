import os
from dotenv import load_dotenv

load_dotenv()

CORS_ORIGINS = [
    'http://localhost:3000',
    'http://localhost:8000',
]

OPENAI_KEY = os.getenv("OPENAI_KEY")
MONGODB_URI = os.getenv("MONGODB_URI")
TOKEN_URI = os.getenv("TOKEN_URI")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
TOPIC_NAME = os.getenv('GMAIL_TOPIC_NAME')



os.environ['OAUTHLIB_RELAX_TOKEN_SCOPE'] = '1'
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'



CLIENT_SECRETS_FILE = "client_secret.json"



API_SERVICE_NAME = 'gmail'
API_VERSION = 'v1'

SCOPES_LIST = ['https://www.googleapis.com/auth/gmail.readonly',
          'https://www.googleapis.com/auth/gmail.modify',
          'https://www.googleapis.com/auth/gmail.labels',
          'https://www.googleapis.com/auth/userinfo.email',
          'https://www.googleapis.com/auth/userinfo.profile',
          'https://mail.google.com/']





labels_list = [
    "Newsletters/Subscriptions",
    "Shopping/Online Orders",
    "Events/Invitations",
    "Receipts/Invoices",
    "Education/School",
    "Health/Wellness",
    "Social Media",
    "Deliveries",
    "Finance",
    "Travel",
    "Alerts",
    "Other",
]

label_color_dict = {
    'Receipts/Invoices': {'name': 'Receipts/Invoices', 'labelListVisibility': 'labelShow',
                          'messageListVisibility': 'show',
                          'color': {'textColor': '#ffffff', 'backgroundColor': '#000000'}},
    'Newsletters/Subscriptions': {'name': 'Newsletters/Subscriptions', 'labelListVisibility': 'labelShow',
                                  'messageListVisibility': 'show',
                                  'color': {'textColor': '#ffffff', 'backgroundColor': '#434343'}},
    'Events/Invitations': {'name': 'Events/Invitations', 'labelListVisibility': 'labelShow',
                           'messageListVisibility': 'show',
                           'color': {'textColor': '#ffffff', 'backgroundColor': '#83334c'}},
    'Education/School': {'name': 'Education/School', 'labelListVisibility': 'labelShow',
                         'messageListVisibility': 'show',
                         'color': {'textColor': '#ffffff', 'backgroundColor': '#cf8933'}},
    'Health/Wellness': {'name': 'Health/Wellness', 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show',
                        'color': {'textColor': '#000000', 'backgroundColor': '#662e37'}},
    'Social Media': {'name': 'Social Media', 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show',
                     'color': {'textColor': '#000000', 'backgroundColor': '#4986e7'}},
    'Deliveries': {'name': 'Deliveries', 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show',
                   'color': {'textColor': '#000000', 'backgroundColor': '#f3f3f3'}},
    'Finance': {'name': 'Finance', 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show',
                'color': {'textColor': '#000000', 'backgroundColor': '#ffffff'}},
    'Shopping/Online Orders': {'name': 'Shopping/Online Orders', 'labelListVisibility': 'labelShow',
                               'messageListVisibility': 'show',
                               'color': {'textColor': '#ffffff', 'backgroundColor': '#fb4c2f'}},
    'Travel': {'name': 'Travel', 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show',
               'color': {'textColor': '#ffffff', 'backgroundColor': '#ffad47'}},
    'Alerts': {'name': 'Alerts', 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show',
               'color': {'textColor': '#ffffff', 'backgroundColor': '#822111'}},
    'Other': {'name': 'Other', 'labelListVisibility': 'labelShow', 'messageListVisibility': 'show',
              'color': {'textColor': '#000000', 'backgroundColor': '#666666'}}
}