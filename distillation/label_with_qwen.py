"""
Label emails with Qwen2.5 via Ollama for training data generation.

This script is ONLY needed if you want to retrain the local DistilBERT model
on your own data. It is NOT part of the normal InboxGuard workflow.

Prerequisites:
  1. Install Ollama: https://ollama.com/download
  2. Pull the model:  ollama pull qwen2.5
  3. Start Ollama:    ollama serve
  4. Run this script from the project root:
       uv run distillation/label_with_qwen.py

What it does:
  - Fetches a random sample of emails from your Gmail inbox
  - Classifies each one using Qwen2.5 running locally via Ollama
  - Writes the labeled results to your Google Sheets (Important / Okay / Spam tabs)
  - Those labels can then be exported with export_training_data.py
    and used to retrain the model with train_student.py
"""

import sys
import os
import json
import time
import requests
from datetime import datetime

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv

load_dotenv()

OLLAMA_URL = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "qwen2.5"
BATCH_SIZE = 50
DEFAULT_SAMPLE = 500


# ── pre-flight checks ─────────────────────────────────────────────────────────

def check_prerequisites():
    errors = []

    if not os.path.exists("credentials.json"):
        errors.append(
            "  ❌  credentials.json not found.\n"
            "      Download it from Google Cloud Console (APIs & Services → Credentials)\n"
            "      and place it in the project root. See README Step 2d."
        )

    if not os.path.exists("token.json"):
        errors.append(
            "  ❌  token.json not found.\n"
            "      You need to authenticate first. Run:  uv run main.py --setup"
        )

    if not os.getenv("SHEET_ID"):
        errors.append(
            "  ❌  SHEET_ID is not set.\n"
            "      Add it to your .env file:  SHEET_ID=your_google_sheet_id\n"
            "      (It's the long ID in your Google Sheets URL)"
        )

    if not os.path.exists("prompts.py"):
        errors.append(
            "  ❌  prompts.py not found.\n"
            "      Create your personalized prompt first. See README → Prompt Setup."
        )

    if errors:
        print("\n  Pre-flight checks failed:\n")
        for e in errors:
            print(e)
        print()
        sys.exit(1)


def check_ollama():
    try:
        resp = requests.get("http://localhost:11434/api/tags", timeout=5)
        resp.raise_for_status()
    except requests.ConnectionError:
        print(
            "\n  ❌  Ollama is not running.\n"
            "      Start it in a separate terminal with:  ollama serve\n"
            "      Then re-run this script.\n"
        )
        sys.exit(1)
    except requests.HTTPError as e:
        print(f"\n  ❌  Ollama returned an unexpected error: {e}\n")
        sys.exit(1)

    models = [m["name"] for m in resp.json().get("models", [])]
    if not any("qwen2.5" in m for m in models):
        print(
            "\n  ❌  qwen2.5 is not installed in Ollama.\n"
            "      Pull it with:  ollama pull qwen2.5\n"
            "      Then re-run this script.\n"
        )
        sys.exit(1)

    print(f"  ✅  Ollama running  |  model: {OLLAMA_MODEL}")


# ── classification ────────────────────────────────────────────────────────────

def call_qwen(prompt: str) -> str:
    payload = {
        "model": OLLAMA_MODEL,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
        "options": {"temperature": 0.1},
    }
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=60)
        resp.raise_for_status()
        return resp.json()["message"]["content"].strip()
    except requests.Timeout:
        raise RuntimeError("Ollama timed out (60s). Your machine may be too slow for this model.")
    except requests.ConnectionError:
        raise RuntimeError("Lost connection to Ollama mid-run. Is 'ollama serve' still running?")
    except requests.HTTPError as e:
        raise RuntimeError(f"Ollama HTTP error: {e}")
    except KeyError:
        raise RuntimeError("Unexpected response format from Ollama.")


def classify_email(sender: str, subject: str, snippet: str) -> dict | None:
    from prompts import CLASSIFICATION_PROMPT

    prompt = f"""{CLASSIFICATION_PROMPT}

From: {sender}
Subject: {subject}
Snippet: {snippet}"""

    try:
        raw = call_qwen(prompt)
        raw = raw.strip().lstrip("```json").lstrip("```").rstrip("```").strip()
        result = json.loads(raw)
        category = result.get("category", "").lower()
        if category not in ("important", "okay", "unwanted"):
            return None
        return {"category": category, "reason": result.get("reason", "qwen2.5")}
    except RuntimeError as e:
        print(f"\n  ❌  Qwen2.5 error: {e}\n")
        sys.exit(1)
    except (json.JSONDecodeError, ValueError):
        return None


# ── main ──────────────────────────────────────────────────────────────────────

def main():
    if len(sys.argv) > 1:
        try:
            sample_size = int(sys.argv[1])
            if sample_size <= 0:
                raise ValueError
        except ValueError:
            print(f"\n  ❌  Invalid sample size '{sys.argv[1]}'. Must be a positive number.\n"
                  "      Usage:  uv run distillation/label_with_qwen.py [sample_size]\n"
                  "      Example: uv run distillation/label_with_qwen.py 1000\n")
            sys.exit(1)
    else:
        sample_size = DEFAULT_SAMPLE

    print("\n  InboxGuard — Label emails with Qwen2.5 (training data)")
    print("  ─────────────────────────────────────────────────────")
    print(f"  Sample size : {sample_size} emails")
    print(f"  Model       : {OLLAMA_MODEL} via Ollama\n")

    check_prerequisites()
    check_ollama()

    print("  Connecting to Gmail...")
    try:
        from gmail_client import get_gmail_service, fetch_random_sample, fetch_emails_batch
        service = get_gmail_service()
    except FileNotFoundError:
        print("\n  ❌  credentials.json is missing or unreadable.\n"
              "      See README Step 2d to download it from Google Cloud Console.\n")
        sys.exit(1)
    except Exception as e:
        print(f"\n  ❌  Gmail connection failed: {e}\n"
              "      Try re-authenticating:  uv run main.py --setup\n")
        sys.exit(1)

    print("  Connecting to Google Sheets...")
    try:
        from sheets_logger import get_sheet, setup_headers, log_emails_batch
        sheets = get_sheet()
        setup_headers(sheets)
    except Exception as e:
        print(f"\n  ❌  Google Sheets connection failed: {e}\n"
              "      Make sure SHEET_ID in .env is correct and the sheet has tabs\n"
              "      named exactly: Important, Okay, Spam\n")
        sys.exit(1)

    print(f"  Fetching {sample_size} random email IDs...")
    try:
        email_ids = fetch_random_sample(service, sample_size)
    except Exception as e:
        print(f"\n  ❌  Failed to fetch emails from Gmail: {e}\n"
              "      Check your internet connection and try again.\n")
        sys.exit(1)

    if not email_ids:
        print("\n  ⚠️  No emails found in your inbox. Nothing to label.\n")
        sys.exit(0)

    print(f"  Found {len(email_ids)} emails\n")

    total = len(email_ids)
    labeled = 0
    failed = 0
    sheets_errors = 0
    logs = []

    for i in range(0, total, BATCH_SIZE):
        batch_ids = email_ids[i:i + BATCH_SIZE]

        try:
            emails, _ = fetch_emails_batch(service, batch_ids)
        except Exception as e:
            print(f"\n  ⚠️  Failed to fetch batch {i}–{i + BATCH_SIZE}: {e} — skipping")
            failed += len(batch_ids)
            continue

        for email in emails:
            sender = email.get("sender", "")
            subject = email.get("subject", "")
            snippet = email.get("snippet", "")

            if not sender and not subject:
                failed += 1
                continue

            result = classify_email(sender, subject, snippet)
            if result is None:
                failed += 1
                continue

            logs.append({
                "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                "sender": sender,
                "subject": subject,
                "category": result["category"],
                "reason": result["reason"],
                "action": "LABELED",
            })
            labeled += 1

        if logs:
            try:
                log_emails_batch(sheets, logs)
                logs = []
            except Exception as e:
                sheets_errors += 1
                if sheets_errors >= 3:
                    print(f"\n  ❌  Google Sheets keeps failing ({e}).\n"
                          "      Check your internet connection and SHEET_ID, then retry.\n")
                    sys.exit(1)
                print(f"\n  ⚠️  Sheets write failed (attempt {sheets_errors}/3): {e} — retrying next batch")

        done = min(i + BATCH_SIZE, total)
        print(f"  [{done}/{total}]  labeled={labeled}  failed={failed}", end="\r")
        time.sleep(0.5)

    if logs:
        try:
            log_emails_batch(sheets, logs)
        except Exception as e:
            print(f"\n  ⚠️  Final Sheets flush failed: {e}\n"
                  "      {len(logs)} labels may not have been saved.")

    print(f"\n\n  ✓ Done — {labeled} emails labeled, {failed} failed/skipped")
    if sheets_errors:
        print(f"  ⚠️  {sheets_errors} Sheets write error(s) occurred — some labels may be missing")
    print("  Labels written to Google Sheets.")
    print("\n  Next steps:")
    print("    1. Review the Sheets tabs and delete any wrong labels")
    print("    2. uv run distillation/export_training_data.py")
    print("    3. uv run distillation/train_student.py")
    print()


if __name__ == "__main__":
    main()
