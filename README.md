# Gmail Cleaner Agent

An AI-powered agent that reads your Gmail inbox, classifies every email as
`important`, `okay`, or `unwanted`, logs the result to a Google Sheet, and
(optionally) trashes the junk for you.

Built to clean out a massively cluttered inbox once, then keep it tidy on a
weekly cron run.

---

## How it works

1. **First run** — fetches every email ID from your inbox, stores them in a
   local SQLite DB as `pending`, and processes them in batches.
2. **Classification** — each email's subject, sender, and snippet are sent to
   an LLM (Groq primary, Gemini fallback) which returns a category + reason.
3. **Logging** — the result is written to one of three tabs in a Google Sheet
   (`Important`, `Okay`, `Spam`).
4. **Action** — `unwanted` emails are moved to trash (skipped when
   `DRY_RUN=True`). Everything else is kept.
5. **Cron runs** — subsequent runs only process new emails since the last run,
   tracked via Gmail's `historyId`.

The SQLite DB (`agent.db`) makes the run resumable — if it crashes mid-batch,
re-running picks up from where it stopped.

---

## Project layout

| File | Purpose |
| --- | --- |
| `main.py` | Orchestrator — runs first-time or cron flow |
| `gmail_client.py` | Gmail API wrapper (auth, fetch, trash, history) |
| `ai_classifier.py` | Prompt + parser for the LLM classification |
| `model.py` | LLM factory (Groq → Gemini fallback) |
| `db_manager.py` | SQLite state + JSON state file for historyId |
| `sheets_logger.py` | gspread wrapper for logging to Google Sheets |
| `config.py` | OAuth scopes |

---

## Setup

### 1. Install dependencies

Requires Python 3.11+. This project uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync
```

Or with pip:

```bash
pip install -e .
```

### 2. Google Cloud setup

You need a Google Cloud project with the following APIs enabled:

- Gmail API
- Google Sheets API
- Google Drive API

Then:

1. Create an **OAuth 2.0 Client ID** (type: Desktop app).
2. Download the credentials JSON and save it as `credentials.json` in the
   project root.
3. On first run, a browser window will open for you to authorize access.
   A `token.json` file is created for future runs.

### 3. Create the Google Sheet

Create a Google Sheet with three tabs named exactly:

- `Important`
- `Okay`
- `Spam`

Copy the sheet's ID from its URL (the long string between `/d/` and `/edit`).

### 4. Environment variables

Create a `.env` file in the project root:

```env
GROQ_API_KEY=your_groq_key_here
GEMINI_API_KEY=your_gemini_key_here
SHEET_ID=your_google_sheet_id_here
```

Get keys from:
- Groq: https://console.groq.com
- Gemini: https://aistudio.google.com/app/apikey

---

## Usage

### Run it

```bash
python main.py
```

- **First run** auto-detects and processes every email in your inbox.
- **Subsequent runs** only process new emails since the last run.

### Dry run mode

By default, `DRY_RUN = True` in `main.py`. Nothing is actually deleted —
emails that would be trashed are just logged with `"Dry run - would delete"`.

Once you trust the classifier, flip it:

```python
# main.py
DRY_RUN = False
```

### Tuning

In `main.py`:

```python
BATCH_SIZE = 50              # emails per batch
DELAY_BETWEEN_BATCHES = 3    # seconds between batches (Groq rate limit)
```

Groq free tier is 30 req/min — the delay keeps you under the limit.

---

## Classification rules

The AI is tuned to be **aggressive** — when in doubt, it classifies as
`unwanted`. Storage is the priority.

| Category | What it catches |
| --- | --- |
| `important` | Bank alerts, OTPs, bills, receipts, job offers, security alerts |
| `okay` | Hackathons, community posts, direct notifications from used platforms |
| `unwanted` | Newsletters, job board spam, course promos, marketing, gamification |

Edit the prompt in `ai_classifier.py` to change the behavior.

---

## State files

Two files track progress. Both are gitignored:

- `agent.db` — SQLite DB of every email ID seen and its status
  (`pending` / `processed` / `failed`).
- `agent_state.json` — stores `is_first_run`, `last_history_id`, `last_run`.
  Used to decide which flow (`first_run` vs `cron`) to execute.

Delete both files to reset state and reprocess everything.

---

## Running on a schedule

Example weekly cron (Linux/macOS):

```cron
0 9 * * 1 cd /path/to/email-agent && /usr/bin/python main.py >> agent.log 2>&1
```

On Windows, use Task Scheduler pointing at `main.py`.

**Note:** Gmail's `historyId` expires after ~30 days of inactivity. If that
happens, the agent falls back to fetching the last 100 emails instead of
crashing.

---

## Troubleshooting

**Auth errors after a while** — delete `token.json` and re-run to re-auth.

**Google Sheets fails on first run** — make sure the three tabs exist with
the exact names `Important`, `Okay`, `Spam`.

**Groq rate-limit errors** — increase `DELAY_BETWEEN_BATCHES` in `main.py`,
or rely on the Gemini fallback.

**Want to reprocess everything** — delete `agent.db` and `agent_state.json`.
