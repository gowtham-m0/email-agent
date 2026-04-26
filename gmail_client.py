import os
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from config import SCOPES


def get_gmail_service():
    creds = None

    if os.path.exists('token.json'):
        try:
            creds = Credentials.from_authorized_user_file('token.json', SCOPES)
        except Exception:
            print("\n  ⚠  Stored token has wrong permissions. Re-authenticating...\n")
            os.remove('token.json')
            creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            print("  ┌─────────────────────────────────────────────────────┐")
            print("  │  🔐  Google Sign-In will open in your browser.      │")
            print("  │                                                     │")
            print("  │  ⚠  IMPORTANT: Grant ALL permissions when asked.   │")
            print("  │     • Gmail (read, send, delete)                    │")
            print("  │     • Google Sheets                                 │")
            print("  │     • Google Drive                                  │")
            print("  │                                                     │")
            print("  │  If you skip any, you will see auth errors later.   │")
            print("  └─────────────────────────────────────────────────────┘\n")
            flow = InstalledAppFlow.from_client_secrets_file(
                'credentials.json', SCOPES
            )
            creds = flow.run_local_server(port=0)

        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return build("gmail", "v1", credentials=creds)


def fetch_emails_batch(service, email_ids: list) -> tuple[list, list]:
    results = []
    errors = []

    def callback(request_id, response, exception):
        if exception is not None:
            errors.append(request_id)
            return
        try:
            headers = response["payload"]["headers"]
            subject = next(
                (h["value"] for h in headers if h["name"] == "Subject"),
                "No Subject"
            )
            sender = next(
                (h["value"] for h in headers if h["name"] == "From"),
                "Unknown"
            )
            snippet = response.get("snippet", "")
            results.append({
                "id": request_id,
                "subject": subject,
                "sender": sender,
                "snippet": snippet,
            })
        except Exception:
            errors.append(request_id)

    batch = service.new_batch_http_request(callback=callback)
    for email_id in email_ids:
        batch.add(
            service.users().messages().get(
                userId="me",
                id=email_id,
                format="metadata",
                metadataHeaders=["Subject", "From"],
            ),
            request_id=email_id,
        )
    batch.execute()
    return results, errors


def trash_emails_batch(service, email_ids: list) -> set:
    if not email_ids:
        return set()

    failed = set()
    for i in range(0, len(email_ids), 1000):
        chunk = email_ids[i:i + 1000]
        try:
            service.users().messages().batchModify(
                userId="me",
                body={
                    "ids": chunk,
                    "addLabelIds": ["TRASH"],
                    "removeLabelIds": ["INBOX", "UNREAD"],
                },
            ).execute()
        except Exception:
            failed.update(chunk)
    return failed


def fetch_all_email_ids(service) -> list:
    ids = []
    page_token = None

    while True:
        params = {
            "userId": "me",
            "maxResults": 500,
            "labelIds": ["INBOX"],
        }
        if page_token:
            params["pageToken"] = page_token

        result = service.users().messages().list(**params).execute()
        messages = result.get("messages", [])
        ids.extend(msg["id"] for msg in messages)

        page_token = result.get("nextPageToken")
        if not page_token:
            break

    return ids


def fetch_random_sample(service, sample_size: int) -> tuple[list, list]:
    import random
    all_ids = fetch_all_email_ids(service)
    random.shuffle(all_ids)
    return all_ids[:sample_size], all_ids[sample_size:]


def get_current_history_id(service) -> str:
    profile = service.users().getProfile(userId="me").execute()
    return profile["historyId"]


def fetch_emails_since_history_id(service, history_id) -> list:
    try:
        seen = set()
        page_token = None

        while True:
            params = {
                "userId": "me",
                "startHistoryId": history_id,
                "historyTypes": ["messageAdded"],
            }
            if page_token:
                params["pageToken"] = page_token

            result = service.users().history().list(**params).execute()

            for record in result.get("history", []):
                for msg in record.get("messages", []):
                    seen.add(msg["id"])

            page_token = result.get("nextPageToken")
            if not page_token:
                break

        return list(seen)

    except Exception:
        return fetch_all_email_ids_limited(service, max_results=100)


def fetch_spam_email_ids(service) -> list:
    ids = []
    page_token = None
    while True:
        params = {
            "userId": "me",
            "maxResults": 500,
            "labelIds": ["SPAM"],
        }
        if page_token:
            params["pageToken"] = page_token
        result = service.users().messages().list(**params).execute()
        messages = result.get("messages", [])
        ids.extend(msg["id"] for msg in messages)
        page_token = result.get("nextPageToken")
        if not page_token:
            break
    return ids


def permanently_delete_batch(service, email_ids: list):
    if not email_ids:
        return
    for i in range(0, len(email_ids), 1000):
        chunk = email_ids[i:i + 1000]
        service.users().messages().batchDelete(
            userId="me",
            body={"ids": chunk},
        ).execute()


def fetch_all_email_ids_limited(service, max_results=100) -> list:
    result = service.users().messages().list(
        userId="me",
        maxResults=max_results,
        labelIds=["INBOX"],
    ).execute()
    messages = result.get("messages", [])
    return [msg["id"] for msg in messages]


def mark_emails_as_read_batch(service, email_ids: list):
    if not email_ids:
        return
    for i in range(0, len(email_ids), 1000):
        chunk = email_ids[i:i + 1000]
        try:
            service.users().messages().batchModify(
                userId="me",
                body={"ids": chunk, "removeLabelIds": ["UNREAD"]},
            ).execute()
        except Exception:
            pass
