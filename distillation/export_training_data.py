import sys, os, json
sys.stdout.reconfigure(encoding='utf-8')
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import gspread
from dotenv import load_dotenv
from auth_helpers import get_google_credentials

load_dotenv()

def export():
    token_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "token.json")
    creds = get_google_credentials(token_path)
    client = gspread.authorize(creds)
    workbook = client.open_by_key(os.getenv("SHEET_ID"))

    tab_to_label = {
        "Important": "important",
        "Okay": "okay",
        "Spam": "unwanted"
    }

    samples = []
    skipped = 0

    for tab_name, label in tab_to_label.items():
        sheet = workbook.worksheet(tab_name)
        rows = sheet.get_all_records()

        for row in rows:
            sender = str(row.get("Sender", "")).strip()
            subject = str(row.get("Subject", "")).strip()
            reason = str(row.get("Reason", "")).strip()

            if "Could not parse" in reason or "Parse failed" in reason:
                skipped += 1
                continue

            if not sender or not subject:
                skipped += 1
                continue

            text = f"From: {sender}\nSubject: {subject}"
            samples.append({"text": text, "label": label})

    output_path = os.path.join(os.path.dirname(__file__), "training_data.jsonl")
    with open(output_path, "w", encoding="utf-8") as f:
        for s in samples:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")

    print(f"✅ Exported {len(samples)} samples ({skipped} skipped)")
    print(f"   Important : {sum(1 for s in samples if s['label'] == 'important')}")
    print(f"   Okay      : {sum(1 for s in samples if s['label'] == 'okay')}")
    print(f"   Unwanted  : {sum(1 for s in samples if s['label'] == 'unwanted')}")
    print(f"💾 Saved to {output_path}")
    return samples

if __name__ == "__main__":
    export()
