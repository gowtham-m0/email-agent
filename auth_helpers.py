import json
import os
import sys

from google.auth.exceptions import RefreshError
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from config import SCOPES


CREDENTIALS_PATH = "credentials.json"
TOKEN_PATH = "token.json"
REQUIRED_SCOPES = set(SCOPES)

Y = "\033[93m"
R = "\033[91m"
B = "\033[1m"
D = "\033[2m"
X = "\033[0m"


def _token_scopes(token_path: str) -> set[str]:
    try:
        with open(token_path, encoding="utf-8") as token_file:
            data = json.load(token_file)
    except (OSError, json.JSONDecodeError):
        return set()

    scopes = data.get("scopes") or data.get("scope") or []
    if isinstance(scopes, str):
        scopes = scopes.split()
    return set(scopes)


def _token_has_required_scopes(token_path: str) -> bool:
    token_scopes = _token_scopes(token_path)
    return REQUIRED_SCOPES.issubset(token_scopes)


def _delete_token(token_path: str) -> None:
    try:
        os.remove(token_path)
    except FileNotFoundError:
        pass


def _print_scope_help(exc: Exception) -> None:
    print(f"\n  {R}Google did not grant every permission InboxGuard requested.{X}")
    print(f"  {D}{exc}{X}\n")
    print(f"  {B}Fix:{X}")
    print("    1. In the browser consent screen, select every checkbox Google shows.")
    print("    2. Grant Gmail, Google Sheets, and Google Drive access together.")
    print("    3. If Google keeps remembering the old choice, revoke the app here:")
    print("       https://myaccount.google.com/permissions")
    print("    4. Run InboxGuard again so it can create a fresh token.json.\n")


def run_oauth_flow(scopes: list[str] | None = None, token_path: str = TOKEN_PATH):
    print("  Google Sign-In will open in your browser.")
    print("  Grant all requested permissions: Gmail, Google Sheets, and Google Drive.")
    print(f"  {Y}If Google shows checkboxes, select all of them before continuing.{X}\n")
    flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_PATH, scopes or SCOPES)
    try:
        return flow.run_local_server(port=0, prompt="consent", include_granted_scopes="true")
    except Exception as exc:
        if "Scope has changed" in str(exc):
            _delete_token(token_path)
            _print_scope_help(exc)
            raise SystemExit(1) from exc
        raise


def _save_credentials(creds, token_path: str) -> None:
    with open(token_path, "w", encoding="utf-8") as token_file:
        token_file.write(creds.to_json())


def get_google_credentials(token_path: str = TOKEN_PATH):
    creds = None

    if os.path.exists(token_path):
        if not _token_has_required_scopes(token_path):
            print("\n  Stored Google token is missing required permissions. Re-authenticating...\n")
            _delete_token(token_path)
        else:
            try:
                creds = Credentials.from_authorized_user_file(token_path, SCOPES)
            except Exception:
                print("\n  Stored Google token could not be loaded. Re-authenticating...\n")
                _delete_token(token_path)
                creds = None

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            try:
                creds.refresh(Request())
            except RefreshError as exc:
                print(f"\n  {R}Google auth token needs fresh consent.{X}")
                print(f"  {D}{exc}{X}\n")
                if sys.stdin.isatty():
                    choice = input(f"  {B}Re-authenticate now?{X}  {D}[1] Yes   [any] Exit:{X}  ").strip()
                    if choice != "1":
                        print(f"\n  {D}Exiting. Run again when ready to re-authenticate.{X}\n")
                        sys.exit(0)
                _delete_token(token_path)
                creds = run_oauth_flow(token_path=token_path)
        else:
            creds = run_oauth_flow(token_path=token_path)

        _save_credentials(creds, token_path)

    return creds