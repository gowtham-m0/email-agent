import time
from gmail_client import (
    get_gmail_service,
    fetch_all_email_ids,
    fetch_email_details,
    fetch_emails_since_history_id,
    get_current_history_id,
    delete_email
)

from ai_classifier import classify_email
from sheets_logger import get_sheet, setup_headers, log_email
from db_manager import (
    setup_database,
    insert_email_ids,
    get_pending_emails,
    mark_processed,
    mark_failed,
    get_stats,
    load_state,
    complete_first_run,
    update_after_cron
)

#CONFIGURATION
BATCH_SIZE = 50
DELAY_BETWEEN_BATCHES = 3
DRY_RUN = True

def process_single_email(service, sheets, email_id: str):
    """
    Fetches, classifies, logs and optionally deletes one email.
    Returns True if successful, False if failed.
    """
    try:
        email = fetch_email_details(service, email_id)

        result = classify_email(
            subject=email["subject"],
            sender=email["sender"],
            snippet=email["snippet"]
        )

        category = result["category"]
        reason = result["reason"]

        if category == "unwanted":
            if DRY_RUN:
                action = "Dry run - would delete"
            else:
                delete_email(service, email_id)
                action = "Deleted"
        else:
            action = "Kept"

        log_email(sheets, email, category, reason, action)
        mark_processed(email_id, category)

        icon = "🗑️" if category == "unwanted" else "✅" if category == "okay" else "📌"
        print(f"  {icon} {category.upper():<10} | {email['subject'][:45]}")

        return True

    except Exception as e:
        print(f"  ❌ Failed to process {email_id}: {e}")
        mark_failed(email_id)
        return False
    

def run_first_time(service, sheets, state):
    """
    First run logic.
    Fetches all email IDs and processes them in batches.
    Can be interrupted and resumed safely.
    """

    print("First run detected.")
    print("Fetching all email IDs...")

    all_ids = fetch_all_email_ids(service)
    print(f"Found {len(all_ids)} emails total.")

    insert_email_ids(all_ids)

    process_in_batches(service, sheets)

    history_id = get_current_history_id(service)
    complete_first_run(history_id)

    print("\n✅ First run complete.")
    print(f"Final stats: {get_stats()}")

def run_cron(service, sheets, state):
    """
    Cron run logic.
    Only fetches emails that arrived since last run.
    """

    print(f"Cron run - fetching new emails since last run ({state['last_run']}).")

    new_ids = fetch_emails_since_history_id(service, state["last_history_id"])

    if not new_ids:
        print("No new emails to process.")
        return

    print(f"Found {len(new_ids)} new emails.")

    insert_email_ids(new_ids)

    process_in_batches(service, sheets)

    history_id = get_current_history_id(service)
    update_after_cron(history_id)

    print("\n✅ Cron complete.")
    print(f"Final stats: {get_stats()}")

def process_in_batches(service, sheets):
    """
    Processes all pending emails from SQLite in batches.
    Shared by first run and cron run.
    """

    batch_number = 0

    while True:
        pending = get_pending_emails(batch_size=BATCH_SIZE)

        if not pending:
            print("\nAll pending emails processed.")
            break

        batch_number += 1
        print(f"\nBatch {batch_number} - processing {len(pending)} emails...")

        success = 0
        failed = 0

        for email_id in pending:
            if process_single_email(service, sheets, email_id):
                success += 1
            else:
                failed += 1

        stats = get_stats()
        total = sum(stats.values())
        processed = stats.get("processed", 0)

        print("-" * 40)
        print(f"Batch {batch_number} summary:  success={success}  failed={failed}")
        print(f"Overall progress:    {processed}/{total} emails processed")
        print("-" * 40)

        # GROQ free tier is 30 req/min and each batch makes BATCH_SIZE requests,
        # so pause between batches to stay under the rate limit.
        print(f"Waiting {DELAY_BETWEEN_BATCHES} seconds before next batch...")
        time.sleep(DELAY_BETWEEN_BATCHES)


def main():
    print("=" * 50)
    print("    Gmail Cleaner Agent")
    print("=" * 50)
    print(f"Dry run:    {DRY_RUN}")
    print(f"Batch size: {BATCH_SIZE}")
    print("=" * 50 + "\n")

    #setup 
    setup_database()
    service = get_gmail_service()
    sheets = get_sheet()
    setup_headers(sheets)
    state = load_state()

    if state["is_first_run"]:
        run_first_time(service, sheets, state)
    else:
        run_cron(service, sheets, state)

if __name__ == "__main__":
    main()