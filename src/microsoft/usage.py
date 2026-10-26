import os

from dotenv import load_dotenv

from src.microsoft.ms_graph_email_client import fetch_user_emails

load_dotenv()  # loads variables from .env

emails = fetch_user_emails(
    client_id=os.environ['MS_CLIENT_ID'],
    client_secret=os.environ['MS_CLIENT_SECRET'],
    tenant_id=os.environ['MS_TENANT_ID'],
    user_email=os.environ['USER_EMAIL'],
    start_datetime='2026-01-01T00:00:00Z',
    end_datetime='2026-02-28T23:59:59Z',
    strip_html=True,  # False → raw HTML: True: extract visible text only
)

if emails:
    print(emails[0])
else:
    print('No emails found in the given date range.')
