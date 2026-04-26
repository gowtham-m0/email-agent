#!/usr/bin/env python3
"""
InboxGuard — AI-powered email cleanup.
Run: uv run main.py
"""

import sys
import os
import time
from datetime import datetime

from gmail_client import (
    get_gmail_service,
    fetch_all_email_ids,
    fetch_emails_batch,
    fetch_emails_since_history_id,
    get_current_history_id,
    fetch_spam_email_ids,
    permanently_delete_batch,
    mark_emails_as_read_batch,
    trash_emails_batch,
    fetch_random_sample,
)
from ai_classifier import classify_emails_batch
from sheets_logger import get_sheet, log_emails_batch, setup_headers
from report_generator import generate_report
from db_manager import (
    setup_database,
    insert_email_ids,
    get_pending_emails,
    mark_processed,
    mark_dry_run,
    reset_dry_run_emails,
    mark_failed,
    get_stats,
    load_state,
    complete_first_run,
    update_after_cron,
)

# ── ANSI helpers ─────────────────────────────────────────────────

C = "\033[96m"   # cyan
G = "\033[92m"   # green
Y = "\033[93m"   # yellow
R = "\033[91m"   # red
B = "\033[1m"    # bold
D = "\033[2m"    # dim
X = "\033[0m"    # reset

BATCH_SIZE = 50


def _enable_ansi():
    """Enable ANSI escape codes on Windows."""
    if sys.platform == "win32":
        try:
            import ctypes
            kernel32 = ctypes.windll.kernel32
            kernel32.SetConsoleMode(kernel32.GetStdHandle(-11), 7)
        except Exception:
            pass


def banner():
    print(f"""
{C}╔══════════════════════════════════════════════════════════════╗
║                                                              ║
║   ██╗███╗   ██╗██████╗  ██████╗ ██╗  ██╗                    ║
║   ██║████╗  ██║██╔══██╗██╔═══██╗╚██╗██╔╝                    ║
║   ██║██╔██╗ ██║██████╔╝██║   ██║ ╚███╔╝                     ║
║   ██║██║╚██╗██║██╔══██╗██║   ██║ ██╔██╗                     ║
║   ██║██║ ╚████║██████╔╝╚██████╔╝██╔╝ ██╗                    ║
║   ╚═╝╚═╝  ╚═══╝╚═════╝  ╚═════╝╚═╝  ╚═╝                    ║
║           {Y}G U A R D{C}       v1.0                              ║
║                                                              ║
║   AI-powered email cleanup for Gmail                         ║
╚══════════════════════════════════════════════════════════════╝{X}
""")


def sep():
    print(f"{C}{'─' * 60}{X}")


def ok(msg):
    print(f"  {G}✓{X} {msg}")


def warn(msg):
    print(f"  {Y}!{X} {msg}")


def err(msg):
    print(f"  {R}✗{X} {msg}")


def info(msg):
    print(f"  {D}>{X} {msg}")


def _interactive():
    return sys.stdin.isatty()


def pause():
    if _interactive():
        input(f"\n  {B}Press Enter to continue...{X}")


def ask(prompt, default=None):
    suffix = f" [{default}]" if default else ""
    val = input(f"\n  {B}{prompt}{suffix}: {X}").strip()
    return val or default


def ask_yn(prompt, default=True):
    tag = "Y/n" if default else "y/N"
    val = input(f"\n  {B}{prompt} [{tag}]: {X}").strip().lower()
    if not val:
        return default
    return val in ("y", "yes")


# ── Menu ─────────────────────────────────────────────────────────

def main_menu():
    banner()
    sep()
    print(f"""
  {B}1{X}.  Process emails
  {B}2{X}.  Clear spam folder
  {B}3{X}.  Exit
""")
    return ask("Choose", "1")


def process_submenu():
    print(f"""
  {B}How do you want to process?{X}
  {C}───────────────────────────────{X}
  {B}1{X}.  {Y}Dry Run{X}       (preview only — nothing deleted)
  {B}2{X}.  {R}Clean Wipe{X}    (classify and DELETE unwanted emails)
  {B}0{X}.  {D}Back{X}
""")
    return ask("Choose", "1")


# ── Setup wizard ─────────────────────────────────────────────────

def setup_wizard():
    banner()
    print(f"  {B}First-Time Setup{X}")
    sep()

    print(f"""
  This wizard walks you through the one-time configuration.

  You will need:
    1. credentials.json from Google Cloud Console
    2. A Google Sheet with tabs: Important, Okay, Spam
    3. A Groq API key for LLM classification fallback
""")

    if not ask_yn("Continue?"):
        return

    # Step 1: Gmail
    print(f"\n  {B}Step 1 — Gmail Authentication{X}")
    sep()
    print("  A browser window will open. Sign in and grant access.")
    print("  Credentials are stored locally in token.json.")
    if ask_yn("Authenticate now?"):
        try:
            service = get_gmail_service()
            ok("Gmail authenticated")
            profile = service.users().getProfile(userId="me").execute()
            ok(f"Signed in as {profile.get('emailAddress', 'unknown')}")
        except Exception as e:
            err(f"Gmail auth failed: {e}")
            return

    # Step 2: Sheets
    print(f"\n  {B}Step 2 — Google Sheets{X}")
    sep()
    print("  Create a Google Sheet with three tabs: Important, Okay, Spam")
    print("  Copy the sheet ID from the URL:")
    print(f"  {D}https://docs.google.com/spreadsheets/d/{{SHEET_ID}}/edit{X}")

    current_id = os.getenv("SHEET_ID", "")
    if current_id:
        info(f"Current SHEET_ID: {current_id[:20]}...")

    sheet_id = ask("Sheet ID (or Enter to skip)")
    if sheet_id:
        _update_env("SHEET_ID", sheet_id)
        ok("SHEET_ID saved to .env")

    # Step 3: Groq
    print(f"\n  {B}Step 3 — Groq API{X}")
    sep()
    print("  Groq provides fast LLM classification for low-confidence emails.")
    print("  Free signup: https://console.groq.com")

    current_key = os.getenv("GROQ_API_KEY", "")
    if current_key:
        info("GROQ_API_KEY already set")
    else:
        key = ask("Groq API key (or Enter to skip)")
        if key:
            _update_env("GROQ_API_KEY", key)
            ok("GROQ_API_KEY saved to .env")
        else:
            warn("Skipped — emails with low model confidence will default to 'okay'")

    # Step 4: Database
    print(f"\n  {B}Step 4 — Database{X}")
    sep()
    setup_database()
    ok("SQLite database ready")

    print(f"\n  {G}Setup complete!{X}")
    print(f"  Run the pipeline with option 1 from the main menu.\n")
    pause()


def _update_env(key: str, value: str):
    env_path = os.path.join(os.path.dirname(__file__), ".env")
    lines = []
    found = False

    if os.path.exists(env_path):
        with open(env_path) as f:
            for line in f:
                if line.strip().startswith(f"{key}="):
                    lines.append(f"{key}={value}\n")
                    found = True
                else:
                    lines.append(line)

    if not found:
        lines.append(f"{key}={value}\n")

    with open(env_path, "w") as f:
        f.writelines(lines)

    os.environ[key] = value


# ── Statistics ───────────────────────────────────────────────────

def show_stats():
    banner()
    print(f"  {B}Statistics{X}")
    sep()

    stats = get_stats()
    total = sum(stats.values())

    if total == 0:
        warn("No emails in database yet. Run the pipeline first.")
        pause()
        return

    processed = stats.get("processed", 0)
    pending   = stats.get("pending", 0)
    failed    = stats.get("failed", 0)

    print(f"""
  Total emails:  {B}{total}{X}
  Processed:     {G}{processed}{X}
  Pending:       {Y}{pending}{X}
  Failed:        {R}{failed}{X}
""")

    if total > 0:
        for status, count in sorted(stats.items(), key=lambda x: -x[1]):
            pct = count / total * 100
            bar_len = int(pct / 2)
            bar = "█" * bar_len + "░" * (50 - bar_len)
            print(f"  {status:12} {bar} {pct:5.1f}%  ({count})")

    print()
    pause()


# ── Pipeline ─────────────────────────────────────────────────────

def run_pipeline(dry_run: bool):
    banner()
    mode = "DRY RUN" if dry_run else "CLEAN WIPE"
    color = Y if dry_run else R
    print(f"  {B}Processing Emails — {color}{mode}{X}")
    sep()

    if not dry_run and "--yes" not in sys.argv and "-y" not in sys.argv:
        print(f"\n  {R}WARNING: This will move unwanted emails to Trash.{X}")
        print(f"  {R}Classification is AI-based and NOT 100% accurate.{X}")
        print(f"  {Y}Run a Dry Run first to review what would be deleted.{X}\n")
        if not ask_yn("I understand the risks. Proceed?", default=False):
            warn("Cancelled.")
            pause()
            return
        print()

    setup_database()

    try:
        service = get_gmail_service()
    except Exception as e:
        err(f"Gmail auth failed: {e}")
        err("Check credentials.json and run: uv run main.py --setup")
        pause()
        return

    try:
        sheets = get_sheet()
        setup_headers(sheets)
    except Exception as e:
        err(f"Google Sheets connection failed: {e}")
        err("Check SHEET_ID in .env")
        pause()
        return

    state = load_state()

    stats = get_stats()
    pending_count = stats.get("pending", 0)

    session_count = 0

    if pending_count > 0:
        info(f"Resuming: {pending_count} emails pending from previous run")
        session_count = pending_count
    elif state["is_first_run"]:
        info("First run — clearing spam folder...")
        _clear_spam(service, dry_run)
        info("Fetching inbox email IDs...")

        if dry_run:
            sample_size = ask("Sample size for preview (e.g., 100, 500, or 'all')", "100")
            if sample_size.lower() == "all":
                all_ids = fetch_all_email_ids(service)
            else:
                try:
                    size = int(sample_size)
                    all_ids = fetch_random_sample(service, size)
                    ok(f"Fetched random sample of {len(all_ids)} emails")
                except ValueError:
                    warn("Invalid input. Using default 100.")
                    all_ids = fetch_random_sample(service, 100)
        else:
            all_ids = fetch_all_email_ids(service)

        ok(f"Found {len(all_ids)} emails to process")
        if len(all_ids) > 500 and not dry_run:
            warn(f"Large batch ({len(all_ids)} emails). This may take a while.")
            if not ask_yn(f"Process all {len(all_ids)} emails?", default=True):
                warn("Cancelled.")
                pause()
                return
        insert_email_ids(all_ids)
        session_count = len(all_ids)
    else:
        info(f"Incremental run (since {state.get('last_run', '?')})")
        new_ids = fetch_emails_since_history_id(service, state["last_history_id"])
        if new_ids:
            ok(f"Found {len(new_ids)} new emails")
            insert_email_ids(new_ids)
        session_count = len(new_ids) if new_ids else 0

    if not dry_run:
        dry_run_count = reset_dry_run_emails()
        if dry_run_count > 0:
            info(f"Re-queuing {dry_run_count} emails from previous dry run")
            session_count += dry_run_count

    if session_count == 0:
        ok("No new emails to process.")
        pause()
        return

    session_counts, session_processed, all_logs, elapsed = _process_batches(
        service, sheets, dry_run, session_count
    )

    if not dry_run:
        history_id = get_current_history_id(service)
        if state["is_first_run"]:
            complete_first_run(history_id)
        else:
            update_after_cron(history_id)

    mode = "dry_run" if dry_run else "clean_wipe"
    report_path = generate_report(all_logs, mode, session_counts, elapsed)
    ok(f"Report saved: {report_path}")

    print()
    sep()
    ok(f"Done! {session_processed}/{session_count} emails processed.")
    sep()

    pause()


def _clear_spam(service, dry_run: bool):
    spam_ids = fetch_spam_email_ids(service)
    if not spam_ids:
        ok("Spam folder empty")
        return
    if dry_run:
        warn(f"DRY RUN: would delete {len(spam_ids)} spam emails")
    else:
        try:
            permanently_delete_batch(service, spam_ids)
            ok(f"Deleted {len(spam_ids)} spam emails")
        except Exception as e:
            err(f"Spam cleanup failed: {e}")


def _live_status(counts, processed, total, elapsed, stage=""):
    imp  = counts.get("important", 0)
    ok_c = counts.get("okay", 0)
    unw  = counts.get("unwanted", 0)
    fail = counts.get("failed", 0)

    if processed > 0 and elapsed > 0:
        rate = processed / elapsed
        remaining = total - processed
        eta = remaining / rate if rate > 0 else 0
        eta_str = f"{eta:.0f}s left"
    else:
        eta_str = "--"

    pct = int(processed / total * 100) if total > 0 else 0
    bar_done = int(pct / 5)
    bar = f"{G}{'█' * bar_done}{X}{D}{'░' * (20 - bar_done)}{X}"

    line = (
        f"\r  {bar} {pct:>3}%  "
        f"{D}|{X} {G}I:{imp}{X} {C}O:{ok_c}{X} {Y}U:{unw}{X} {R}F:{fail}{X} "
        f"{D}|{X} {processed}/{total} "
        f"{D}|{X} {elapsed:.0f}s ({eta_str})"
    )
    if stage:
        line += f" {D}| {stage}{X}"

    sys.stdout.write(line + "  ")
    sys.stdout.flush()


def _process_batches(service, sheets, dry_run: bool, session_total: int = 0):
    if session_total == 0:
        stats = get_stats()
        session_total = stats.get("pending", 0)
    if session_total == 0:
        ok("No pending emails.")
        return {"important": 0, "okay": 0, "unwanted": 0, "failed": 0}, 0, [], 0

    print(f"\n  {B}Processing {session_total} emails...{X}")
    sep()

    global_counts = {"important": 0, "okay": 0, "unwanted": 0, "failed": 0}
    global_processed = 0
    global_start = time.time()
    batch_num = 0
    all_logs = []

    while True:
        pending_ids = get_pending_emails(batch_size=BATCH_SIZE)
        if not pending_ids:
            break

        batch_num += 1

        _live_status(global_counts, global_processed, session_total,
                     time.time() - global_start, f"batch {batch_num}: fetching")

        emails, fetch_errors = fetch_emails_batch(service, pending_ids)
        if fetch_errors:
            for eid in fetch_errors:
                mark_processed(eid, "deleted")
            global_processed += len(fetch_errors)
        if not emails:
            continue

        _live_status(global_counts, global_processed, session_total,
                     time.time() - global_start, f"batch {batch_num}: classifying")

        classified = classify_emails_batch(emails)

        logs = []
        emails_to_mark_read = []
        emails_to_trash = []
        pending_results = []

        for result in classified:
            email_id = result["id"]
            category = result.get("category", "okay")
            error    = result.get("error")

            if error:
                mark_failed(email_id)
                global_counts["failed"] += 1
                global_processed += 1
                _live_status(global_counts, global_processed, session_total,
                             time.time() - global_start)
                continue

            if category == "unwanted" and not dry_run:
                emails_to_trash.append(email_id)

            pending_results.append(result)

        failed_deletes = set()
        if emails_to_trash:
            _live_status(global_counts, global_processed, session_total,
                         time.time() - global_start,
                         f"batch {batch_num}: trashing {len(emails_to_trash)}")
            failed_deletes = trash_emails_batch(service, emails_to_trash)

        for result in pending_results:
            email_id = result["id"]
            category = result.get("category", "okay")
            reason   = result.get("reason", "")

            if category == "unwanted":
                if dry_run:
                    action = "DRY_RUN"
                    mark_dry_run(email_id, category)
                elif email_id in failed_deletes:
                    action = "DELETE_FAILED"
                    mark_failed(email_id)
                    global_counts["failed"] += 1
                    global_processed += 1
                    _live_status(global_counts, global_processed, session_total,
                                 time.time() - global_start)
                    continue
                else:
                    action = "DELETED"
                    mark_processed(email_id, category)
            else:
                action = "KEPT"
                if category == "okay":
                    emails_to_mark_read.append(email_id)
                mark_processed(email_id, category)

            global_counts[category] = global_counts.get(category, 0) + 1
            global_processed += 1

            logs.append({
                "date":     datetime.now().strftime("%Y-%m-%d %H:%M"),
                "sender":   result.get("sender", ""),
                "subject":  result.get("subject", ""),
                "category": category,
                "reason":   reason,
                "action":   action,
            })

            _live_status(global_counts, global_processed, session_total,
                         time.time() - global_start)

        if emails_to_mark_read and not dry_run:
            _live_status(global_counts, global_processed, session_total,
                         time.time() - global_start, "marking as read")
            mark_emails_as_read_batch(service, emails_to_mark_read)

        if logs and not dry_run:
            _live_status(global_counts, global_processed, session_total,
                         time.time() - global_start, "logging to sheets")
            log_emails_batch(sheets, logs)

        all_logs.extend(logs)
        time.sleep(0.3)

    # Clear the progress line
    sys.stdout.write("\033[2K\r")
    sys.stdout.flush()

    elapsed = time.time() - global_start
    print(f"\n  {B}Results{X}")
    sep()
    print(f"    {G}Important:{X}  {global_counts['important']}")
    print(f"    {C}Okay:{X}       {global_counts['okay']}")
    print(f"    {Y}Unwanted:{X}   {global_counts['unwanted']}")
    print(f"    {R}Failed:{X}     {global_counts['failed']}")
    print(f"    {D}Time:{X}       {elapsed:.1f}s")

    return global_counts, global_processed, all_logs, elapsed


# ── Entry point ──────────────────────────────────────────────────

def main():
    _enable_ansi()

    if "--dry-run" in sys.argv:
        run_pipeline(dry_run=True)
        return
    if "--full" in sys.argv:
        run_pipeline(dry_run=False)
        return
    if "--setup" in sys.argv:
        setup_wizard()
        return
    if "--stats" in sys.argv:
        setup_database()
        show_stats()
        return

    while True:
        choice = main_menu()

        if choice == "1":
            sub = process_submenu()
            if sub == "1":
                run_pipeline(dry_run=True)
            elif sub == "2":
                run_pipeline(dry_run=False)
        elif choice == "2":
            try:
                service = get_gmail_service()
                _clear_spam(service, dry_run=False)
            except Exception as e:
                err(f"Failed: {e}")
            pause()
        elif choice == "3":
            ok("See you next time!")
            break
        else:
            warn("Invalid choice")
            time.sleep(0.3)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n\n  {Y}Cancelled.{X}")
        sys.exit(130)
