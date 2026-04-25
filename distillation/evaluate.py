
import os
import sys
import json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from collections import Counter, defaultdict
from transformers import pipeline


SHEET_PATH = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "email.xlsx"

)
MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)),
    "email-classifier-final"
)
CONFIDENCE_THRESHOLD = 0.85

# sheet name → true label
SHEET_LABEL_MAP = {
    "Important": "important",
    "Okay":      "okay",
    "Spam":      "unwanted",
}


def load_sheets(path: str) -> list[dict]:
    """Load all emails from Excel with their true labels."""
    print(f"📥 Loading {path}...")
    all_sheets = pd.read_excel(path, sheet_name=None)
    samples = []
    for sheet_name, true_label in SHEET_LABEL_MAP.items():
        if sheet_name not in all_sheets:
            print(f"  ⚠️  Sheet '{sheet_name}' not found, skipping")
            continue
        df = all_sheets[sheet_name]
        for _, row in df.iterrows():
            sender  = str(row.get("Sender",  "")).strip()
            subject = str(row.get("Subject", "")).strip()
            if not sender and not subject:
                continue
            samples.append({
                "sender":     sender,
                "subject":    subject,
                "true_label": true_label,
                "text":       f"From: {sender}\nSubject: {subject}",
            })
        print(f"  ✅ {sheet_name}: {len(df)} emails (label='{true_label}')")
    return samples


def run_inference(samples: list[dict], model_path: str) -> list[dict]:
    """Run student model on all samples."""
    print(f"\n🤖 Loading student model from {model_path}...")
    clf = pipeline("text-classification", model=model_path, device=-1)
    print(f"✅ Model loaded")

    texts = [s["text"] for s in samples]

    print(f"🔄 Running inference on {len(texts)} emails...")
    # batch inference — much faster than one by one
    results = clf(texts, batch_size=64, truncation=True, max_length=256)
    print(f"✅ Inference complete")

    for sample, result in zip(samples, results):
        sample["pred_label"] = result["label"]
        sample["confidence"] = round(result["score"], 4)
        sample["trusted"]    = result["score"] >= CONFIDENCE_THRESHOLD

    return samples


def analyze(samples: list[dict]):
    """Print full analysis."""
    total = len(samples)
    trusted = [s for s in samples if s["trusted"]]
    untrusted = [s for s in samples if not s["trusted"]]

    correct   = [s for s in samples if s["pred_label"] == s["true_label"]]
    incorrect = [s for s in samples if s["pred_label"] != s["true_label"]]

    correct_trusted = [s for s in trusted if s["pred_label"] == s["true_label"]]

    print(f"\n{'=' * 65}")
    print(f"📊 OVERALL RESULTS")
    print(f"{'=' * 65}")
    print(f"  Total emails      : {total}")
    print(f"  Overall accuracy  : {len(correct)/total*100:.1f}%  ({len(correct)}/{total})")
    print(f"  Trusted (≥{CONFIDENCE_THRESHOLD:.0%}) : {len(trusted)} ({len(trusted)/total*100:.1f}%)")
    if trusted:
        print(f"  Accuracy (trusted): {len(correct_trusted)/len(trusted)*100:.1f}%  ({len(correct_trusted)}/{len(trusted)})")
    print(f"  Low confidence    : {len(untrusted)} → would fall back to Ollama")

    # per-class breakdown
    print(f"\n{'=' * 65}")
    print(f"📋 PER-CLASS ACCURACY")
    print(f"{'=' * 65}")
    print(f"  {'Label':<12} {'Total':>6} {'Correct':>8} {'Accuracy':>10} {'Avg Conf':>10}")
    print(f"  {'-'*12} {'-'*6} {'-'*8} {'-'*10} {'-'*10}")

    for label in ["important", "okay", "unwanted"]:
        label_samples = [s for s in samples if s["true_label"] == label]
        label_correct = [s for s in label_samples if s["pred_label"] == label]
        avg_conf = sum(s["confidence"] for s in label_samples) / len(label_samples) if label_samples else 0
        acc = len(label_correct) / len(label_samples) * 100 if label_samples else 0
        print(f"  {label:<12} {len(label_samples):>6} {len(label_correct):>8} {acc:>9.1f}% {avg_conf:>9.1%}")

    # confusion matrix
    print(f"\n{'=' * 65}")
    print(f"🔀 CONFUSION MATRIX (rows=true, cols=predicted)")
    print(f"{'=' * 65}")
    labels = ["important", "okay", "unwanted"]
    confusion = defaultdict(Counter)
    for s in samples:
        confusion[s["true_label"]][s["pred_label"]] += 1

    header = f"  {'':12}" + "".join(f"{l:>12}" for l in labels)
    print(header)
    for true_l in labels:
        row = f"  {true_l:<12}" + "".join(f"{confusion[true_l][pred_l]:>12}" for pred_l in labels)
        print(row)

    # misclassifications
    print(f"\n{'=' * 65}")
    print(f"❌ MISCLASSIFICATIONS ({len(incorrect)} total)")
    print(f"{'=' * 65}")

    # group by error type
    error_groups = defaultdict(list)
    for s in incorrect:
        key = f"{s['true_label']} → {s['pred_label']}"
        error_groups[key].append(s)

    for error_type, errors in sorted(error_groups.items(), key=lambda x: -len(x[1])):
        print(f"\n  [{error_type}] — {len(errors)} cases")
        # show worst confidence errors first (most wrong)
        errors_sorted = sorted(errors, key=lambda x: x["confidence"])
        for e in errors_sorted[:10]:  # show top 10 per error type
            sender_short = e["sender"][:35] if len(e["sender"]) > 35 else e["sender"]
            subject_short = e["subject"][:50] if len(e["subject"]) > 50 else e["subject"]
            print(f"    conf={e['confidence']:.2f} | {subject_short}")
            print(f"           from: {sender_short}")
        if len(errors) > 10:
            print(f"    ... and {len(errors) - 10} more")

    # confidence distribution
    print(f"\n{'=' * 65}")
    print(f"📈 CONFIDENCE DISTRIBUTION")
    print(f"{'=' * 65}")
    buckets = {"<0.70": 0, "0.70-0.80": 0, "0.80-0.85": 0, "0.85-0.90": 0, "0.90-0.95": 0, "≥0.95": 0}
    for s in samples:
        c = s["confidence"]
        if c < 0.70:        buckets["<0.70"] += 1
        elif c < 0.80:      buckets["0.70-0.80"] += 1
        elif c < 0.85:      buckets["0.80-0.85"] += 1
        elif c < 0.90:      buckets["0.85-0.90"] += 1
        elif c < 0.95:      buckets["0.90-0.95"] += 1
        else:               buckets["≥0.95"] += 1

    for bucket, count in buckets.items():
        bar = "█" * (count // 50)
        marker = " ← threshold" if bucket == "0.85-0.90" else ""
        print(f"  {bucket:>12}: {count:5d} {bar}{marker}")

    # save misclassifications to file
    out_path = os.path.join(os.path.dirname(__file__), "misclassifications.jsonl")
    with open(out_path, "w", encoding="utf-8") as f:
        for s in incorrect:
            f.write(json.dumps({
                "true":    s["true_label"],
                "pred":    s["pred_label"],
                "conf":    s["confidence"],
                "sender":  s["sender"],
                "subject": s["subject"],
            }) + "\n")
    print(f"\n💾 Misclassifications saved to {out_path}")
    print(f"\n✅ Done!")


def main():
    if not os.path.exists(MODEL_PATH):
        print(f"❌ Model not found at {MODEL_PATH}")
        print("   Run train_student.py first!")
        return

    # check for Excel file
    global SHEET_PATH
    if not os.path.exists(SHEET_PATH):
        # try uploads folder
        alt_path = r"C:\Users\user\Downloads\Email_Cleaner_log__3_.xlsx"
        if os.path.exists(alt_path):
            SHEET_PATH = alt_path
        else:
            print(f"❌ Excel file not found at {SHEET_PATH}")
            print("   Update SHEET_PATH in this script.")
            return

    samples = load_sheets(SHEET_PATH)
    print(f"\n📊 Total samples loaded: {len(samples)}")

    samples = run_inference(samples, MODEL_PATH)
    analyze(samples)


if __name__ == "__main__":
    main()