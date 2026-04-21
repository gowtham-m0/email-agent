import os 
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from config import SCOPES



def get_gmail_service():
    """ Authenticate and return the Gmail API service """
    creds = None

    # token.json stores the user's access/refresh tokens
    # it gets created automatically after first login
    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)

    # if no valid credentials, ask user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES
            )
            creds = flow.run_local_server(port=0)
        
        # save credentials for next run

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)

def fetch_emails(service, max_results=50):
    """Fetch recent emails and returns list of {id, subject, sender, snippet}."""

    result = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        labelIds=["INBOX"]
    ).execute()

    messages = result.get("messages", [])
    print(f"Fetched {len(messages)} emails.")
    emails = []

    for msg in messages:
        # fetch full message details
        full_msg = service.users().messages().get(
            userId="me",
            id=msg["id"],
            metadataHeaders=["Subject", "From"]
        ).execute()
    
        headers = full_msg["payload"]["headers"]

        subject = next((h["value"] for h in headers if h["name"] == "Subject"), "No Subject")
        sender = next((h["value"] for h in headers if h["name"] == "From"), "Unknown Sender")
        snippet = full_msg.get("snippet", "")

        emails.append({
            "id": msg["id"],
            "subject": subject,
            "sender": sender,
            "snippet": snippet
        })


    return emails

def delete_email(service, email_id):

    """ Move an email to trash."""

    service.users().messages().trash(
        userId="me",
        id=email_id
    ).execute()

    print(f"Email {email_id} moved to trash.")


def fetch_email_details(service, email_id):

    """
    Fetches subject, sender and snippet for a single email ID.
    Called during batch processing - one email at a time.
    """

    full_msg = service.users().messages().get(
        userId="me",
        id=email_id,
        metadataHeaders=["Subject", "From"]
    ).execute()

    headers = full_msg["payload"]["headers"]

    subject = next(
        (h["value"] for h in headers if h["name"]=="Subject"),
        "No Subject"
    )

    sender = next(
        (h["value"] for h in headers if h["name"]=="From"),
        "Unknown"
    )

    snippet = full_msg.get("snippet", "")

    return {
        "id": email_id,
        "subject": subject,
        "sender": sender,
        "snippet": snippet
    
    }

def fetch_all_email_ids(service):
    """
    First run only.
    Fetches every email ID from Gmail using pagination.
    Returns flat list of ID strings.
    """

    ids = []
    page_token = None

    while True:
        params = {
            "userId": "me",
            "maxResults": 500
        }

        if page_token:
            params["pageToken"] = page_token

        result = service.users().messages().list(**params).execute()

        messages = result.get("messages", [])
        ids.extend([msg["id"] for msg in messages])

        print(f"Fetched {len(ids)} email IDs so far...")

        page_token = result.get("nextPageToken")

        if not page_token:
            break

    print(f"Done. {len(ids)} email IDs fetched in total.")
    return ids

def get_current_history_id(service) -> str:
    """
    Gets Gmail's current historyId.
    This is Gmail's internal counter that increments
    every time anything changes in your mailbox.
    We save this after each run and use it next time
    to fetch only what changed since then.
    """

    profile = service.users().getProfile(userId="me").execute()
    return profile["historyId"]

def fetch_emails_since_history_id(service, history_id) -> list:
    """
    Cron run only.
    Fetches only emails that arrived after the given historyId.
    Falls back to last 100 emails if historyId expired.
    """

    try:
        result = service.users().history().list(
            userId="me",
            startHistoryId=history_id,
            historyTypes=["messagesAdded"]
        ).execute()

        new_ids = []
        for record in result.get("history", []):
            for msg in record.get("messages", []):
                if msg["id"] not in new_ids:
                    new_ids.append(msg["id"])

        print(f"Fetched {len(new_ids)} new emails.")
        return new_ids

    except Exception as e:
        # historyId expires after ~30 days — fall back instead of crashing.
        print(f"historyId expired: {e}")
        print("Falling back to last 100 emails...")
        return fetch_all_email_ids_limited(service, max_results=100)

def fetch_all_email_ids_limited(service, max_results=100) -> list:
    """
    Fallback function when historyId expires.
    Fetches last N email IDs from inbox.
    """

    result = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        labelIds=["INBOX"]
    ).execute()

    messages = result.get("messages", [])
    return [msg["id"] for msg in messages]




