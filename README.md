# InboxGuard — AI-Powered Gmail Cleaner

Automatically classifies every email in your Gmail inbox as **important / okay / unwanted**, logs decisions to Google Sheets, and optionally deletes unwanted mail. Runs on your machine or fully automated via GitHub Actions / system cron.

> **⚠️ Disclaimer:** Classification is AI-based and **not 100% accurate** — important emails may occasionally be misclassified. **Always run with Dry Run first** and review the Google Sheets log before enabling deletion. The author is not responsible for any accidentally deleted emails. Use at your own risk.

---

## How it works

```
Gmail API  →  DistilBERT (local AI model)  →  Google Sheets log
                        ↓ low-confidence
                    Groq API (fast, free)
```

- **Local DistilBERT model** handles ~80–90 % of emails instantly
- **Groq API** fallback for low-confidence cases
- **SQLite** tracks state — safe to stop and resume mid-run
- **Google Sheets** audit log with tabs: `Important`, `Okay`, `Spam`

---

## Prerequisites

Before you start, make sure you have the following installed:

| Tool | Required | Notes |
|------|----------|-------|
| **Python 3.11+** | Yes | [python.org/downloads](https://www.python.org/downloads/) |
| **uv** (package manager) | Yes | Installed automatically by `InboxGuard.bat` on Windows, or see below |
| **Git** | Yes (to clone) | [git-scm.com](https://git-scm.com/) |
| **GPU (CUDA)** | No | Speeds up the local AI model; falls back to CPU automatically |

### Install `uv` manually (if not using the .bat file)

**Windows (PowerShell):**
```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

**macOS / Linux:**
```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installing, restart your terminal and verify:
```bash
uv --version
```

---

## Step 1 — Clone the repository

```bash
git clone https://github.com/gowtham-m0/email-agent.git
cd email-agent
```

---

## Step 2 — Google Cloud Setup (one-time)

Because this app can permanently delete emails, Google requires its own OAuth credentials. You must create them yourself — this is a one-time process.

### 2a. Create a Google Cloud project

1. Go to [console.cloud.google.com](https://console.cloud.google.com/).
2. Click the project dropdown at the top → **New Project**.
3. Name it anything (e.g., `InboxGuard`) and click **Create**.
4. Make sure the new project is selected in the dropdown.

### 2b. Enable the required APIs

1. Go to **APIs & Services → Library** (left sidebar).
2. Search for **Gmail API** → click it → click **Enable**.
3. Go back to Library, search for **Google Sheets API** → click it → click **Enable**.

### 2c. Configure the OAuth consent screen

1. Go to **APIs & Services → OAuth consent screen**.
2. Select **External** → click **Create**.
3. Fill in the required fields:
   - **App name**: `InboxGuard` (or anything)
   - **User support email**: your Gmail address
   - **Developer contact email**: your Gmail address
4. Click **Save and Continue**.
5. On the **Scopes** page, click **Add or Remove Scopes** and manually add:
   - `https://mail.google.com/` ← required to read and delete emails
   - `https://www.googleapis.com/auth/spreadsheets` ← required to log to Sheets
6. Click **Update** → **Save and Continue**.
7. On the **Test users** page, click **Add Users** and add your Gmail address.
8. Click **Save and Continue** → **Back to Dashboard**.

### 2d. Create OAuth credentials

1. Go to **APIs & Services → Credentials**.
2. Click **Create Credentials → OAuth client ID**.
3. Set **Application type** to **Desktop app**.
4. Click **Create**.
5. Click **Download JSON** on the dialog that appears (or the download icon next to the credential).
6. Rename the downloaded file to **`credentials.json`**.
7. Move `credentials.json` into the root of this project folder (same folder as `main.py`).

> ⚠️ Never commit `credentials.json` to Git. It is already in `.gitignore`.

---

## Step 3 — Google Sheets Setup

1. Go to [sheets.google.com](https://sheets.google.com) and create a **new blank spreadsheet**.
2. At the bottom, rename the default tab to `Important`.
3. Click the **+** button to add two more tabs, named exactly:
   - `Okay`
   - `Spam`
4. Copy the **Sheet ID** from the browser URL. It is the long string between `/d/` and `/edit`:
   ```
   https://docs.google.com/spreadsheets/d/1BxiMVs0X_YOUR_ID_HERE/edit
                                          ^^^^^^^^^^^^^^^^^^^^^^^^
   ```
5. Save this ID — you will paste it into `.env` in the next step.

---

## Step 4 — Create the `.env` file

Copy the example file:

```bash
# Windows
copy .env.example .env

# macOS / Linux
cp .env.example .env
```

Open `.env` in any text editor and fill in your values:

```env
# Required
SHEET_ID=your-sheet-id-here

# Recommended — free at console.groq.com
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxx

# Optional: override default Groq model
# GROQ_MODEL=meta-llama/llama-4-scout-17b-16e-instruct
```

### Get a free Groq API key (recommended)

Groq is used as the LLM fallback when the local model is unsure. Without it, low-confidence emails default to "okay".

1. Go to [console.groq.com](https://console.groq.com/).
2. Sign up for a free account.
3. Go to **API Keys → Create API Key**.
4. Copy the key and paste it as `GROQ_API_KEY=` in your `.env` file.

---

## Step 5 — Install dependencies

```bash
uv sync
```

This downloads a sandboxed Python environment and installs all required packages. You only need to run this once (or after pulling updates).

---

## Step 6 — First run & Gmail authentication

Run the interactive setup wizard:

```bash
uv run main.py --setup
```

This will:
1. Open your browser to authenticate with Gmail (you will see a Google sign-in page).
2. Ask you to grant the requested permissions.
3. Save an auth token to `token.json` locally (never shared).
4. Confirm your Google Sheet ID.
5. Initialize the local SQLite database.

> After this step, `token.json` exists. The app never asks you to log in again unless the token expires.

---

## Step 7 — Run the cleaner

### Option A — Interactive menu (recommended for first time)

```bash
uv run main.py
```

You will see a menu:
- **1 → Process emails → 1 (Dry Run)**: classifies everything, logs to Sheets, deletes nothing. **Always do this first.**
- **1 → Process emails → 2 (Clean Wipe)**: classifies and moves unwanted emails to Trash (recoverable within 30 days).
- **2 → Clear spam folder**: empties the Gmail spam/junk folder.

### Option B — Command-line flags (for scripting / cron)

```bash
uv run main.py --dry-run   # preview only, no deletions
uv run main.py --full      # classify and delete unwanted emails
uv run main.py --stats     # show database statistics
uv run main.py --setup     # re-run the setup wizard
```

### Option C — Windows batch file (no terminal needed)

Double-click **`InboxGuard.bat`**.

This script automatically:
1. Checks if `uv` is installed; installs it if missing.
2. Syncs all Python dependencies.
3. Launches the interactive menu.

### Option D — Compiled executable (no Python required)

```text
dist/InboxGuard.exe
```

Keep these files **in the same folder** as the `.exe`:
- `credentials.json`
- `.env`
- `token.json` (created on first run)
- `email-classifier-final/` (the local AI model folder)

---

## Step 8 — Review the Google Sheets log

After every run, open your Google Sheet. You will find:
- **Important** tab — emails kept as high priority
- **Okay** tab — emails kept as normal
- **Spam** tab — emails classified as unwanted (and deleted if not a dry run)

Each row shows: `Date | Sender | Subject | Category | Reason | Action`

**Review this carefully after your first dry run before enabling deletions.**

> **🗑️ Deleted emails go to Trash, not permanent delete.** If you spot a misclassified email in the Spam tab, you can recover it from Gmail Trash within **30 days** — go to Gmail → Trash, find the email, and click **Move to Inbox**.

---

## Setting up automated runs (Cron / Scheduler)

You can schedule InboxGuard to run automatically so your inbox stays clean without manual effort.

### Windows — Task Scheduler

1. Open **Task Scheduler** (search for it in the Start menu).
2. Click **Create Basic Task** in the right panel.
3. **Name**: `InboxGuard Email Cleaner`
4. **Trigger**: Choose your schedule (e.g., Weekly, every Sunday at 8:00 AM).
5. **Action**: Select **Start a program**.
6. **Program/script**: Browse to `InboxGuard.bat`, or enter the full path:
   ```
   C:\path\to\email-agent\InboxGuard.bat
   ```
   Alternatively, to run without a window using `uv` directly:
   - **Program**: `cmd`
   - **Arguments**: `/c "cd /d C:\path\to\email-agent && uv run main.py --full"`
7. Click **Finish**.

To verify it works, right-click the task → **Run**.

> **Tip**: Check **"Run whether user is logged on or not"** in task properties so it runs even when you are away.

---

### macOS / Linux — crontab

1. Open your terminal.
2. Edit your crontab:
   ```bash
   crontab -e
   ```
3. Add a line at the bottom. The format is:
   ```
   MINUTE  HOUR  DAY  MONTH  WEEKDAY  COMMAND
   ```

   **Examples:**

   Run every Sunday at 8:00 AM:
   ```cron
   0 8 * * 0  cd /path/to/email-agent && uv run main.py --full >> ~/inboxguard.log 2>&1
   ```

   Run every day at 7:00 AM:
   ```cron
   0 7 * * *  cd /path/to/email-agent && uv run main.py --full >> ~/inboxguard.log 2>&1
   ```

   Run every Monday and Thursday at 9:00 AM:
   ```cron
   0 9 * * 1,4  cd /path/to/email-agent && uv run main.py --full >> ~/inboxguard.log 2>&1
   ```

4. Save and exit (`:wq` in vim, `Ctrl+X` then `Y` in nano).
5. Verify the crontab was saved:
   ```bash
   crontab -l
   ```

**Find `uv`'s full path** (needed if cron can't find it):
```bash
which uv
# Example output: /home/youruser/.local/bin/uv
```

Then use the full path in crontab:
```cron
0 8 * * 0  cd /path/to/email-agent && /home/youruser/.local/bin/uv run main.py --full >> ~/inboxguard.log 2>&1
```

**View the log:**
```bash
tail -f ~/inboxguard.log
```

---

### GitHub Actions — Fully automated in the cloud (no machine needed)

The repo includes a pre-configured workflow at `.github/workflows/email_cleaner.yml` that runs every Sunday at midnight UTC. This lets InboxGuard run without your computer being on.

#### Setup steps

**1. Fork this repository** to your own GitHub account.

**2. Get your `token.json`**

Run the app locally once to authenticate (Step 6 above). This creates `token.json` in the project folder.

**3. Add GitHub Secrets**

Go to your forked repo on GitHub → **Settings → Secrets and variables → Actions → New repository secret**. Add all of these:

| Secret name | Value | How to get it |
|-------------|-------|---------------|
| `CREDENTIALS_JSON` | Full contents of your `credentials.json` file | Open the file, copy everything |
| `TOKEN_JSON` | Full contents of your `token.json` file | Open the file (created after first local run), copy everything |
| `GROQ_API_KEY` | Your Groq API key | From [console.groq.com](https://console.groq.com/) |
| `SHEET_ID` | Your Google Sheet ID | From the Sheets URL |
| `PROMPTS_PY` | Full contents of your `prompts.py` file | Open the file, copy everything |

**4. Change the schedule** (optional)

Edit `.github/workflows/email_cleaner.yml` line 5:
```yaml
- cron: '0 0 * * 0'   # Every Sunday midnight UTC
```

Cron format: `MINUTE HOUR DAY MONTH WEEKDAY`. Examples:
- `0 8 * * 1` — Every Monday at 8:00 AM UTC
- `0 6 * * *` — Every day at 6:00 AM UTC
- `0 0 1 * *` — First of every month at midnight UTC

**5. Enable Actions** on your fork:

Go to **Actions** tab → click **"I understand my workflows, go ahead and enable them"**.

**6. Test it manually**

Go to **Actions → Email Cleaner Agent → Run workflow → Run workflow**.

Watch the logs to confirm everything works.

> ⚠️ GitHub Actions runs without a GPU, so the local DistilBERT model uses CPU — it is slower but works. The Groq fallback is fast regardless.

---

## Project structure

| File / Folder | Purpose |
|---------------|---------|
| `main.py` | CLI entry point, interactive menu, pipeline orchestration |
| `ai_classifier.py` | Local model → LLM fallback classification pipeline |
| `model.py` | Groq client + DistilBERT wrapper |
| `gmail_client.py` | Gmail API: fetch, delete, history-based incremental sync |
| `sheets_logger.py` | Google Sheets batch logging |
| `db_manager.py` | SQLite state persistence (tracks what has been processed) |
| `config.py` | Shared constants and API scopes |
| `prompts.py` | Classification prompt (version-controlled separately) |
| `credentials.json` | Your OAuth credentials — **never commit this** |
| `token.json` | Your Gmail auth token — auto-created on first run, **never commit** |
| `.env` | Your environment variables — **never commit this** |
| `agent.db` | SQLite database — auto-created, safe to delete to reset state |
| `distillation/` | Scripts used to train the local AI model (not needed to run the app) |
| `email-classifier-final/` | Trained local DistilBERT model weights |
| `InboxGuard.bat` | Windows one-click launcher |

---

## Environment variables reference

Full list of supported variables in `.env`:

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `SHEET_ID` | **Yes** | — | Google Sheet ID for the audit log |
| `GROQ_API_KEY` | Recommended | — | Groq API key for fast LLM fallback |
| `GROQ_MODEL` | No | `meta-llama/llama-4-scout-17b-16e-instruct` | Override the Groq model |

---

## Troubleshooting

**`credentials.json not found`**
Make sure you downloaded the file from Google Cloud Console (Step 2d) and placed it in the same folder as `main.py`.

**`SHEET_ID not set` or Sheets error**
Check that `SHEET_ID` is correctly set in your `.env` file and that the sheet has tabs named exactly `Important`, `Okay`, and `Spam`.

**`ModuleNotFoundError`**
Run `uv sync` to install dependencies.

**Browser does not open during auth**
Copy the URL printed in the terminal and paste it manually into your browser.

**`token.json` expired**
Delete `token.json` and run `uv run main.py --setup` to re-authenticate.

**GitHub Actions: "DRY_RUN is still True"**
The workflow checks that you have not left dry-run mode on. Make sure `DRY_RUN` is not hardcoded to `True` in `main.py`.

**Emails are being misclassified**
Run a dry run first, review the Sheets log, and identify patterns. The model is not perfect — check the "Reason" column to understand why an email was classified a certain way.

---

## License

MIT
