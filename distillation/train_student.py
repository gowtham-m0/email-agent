import sys, os, json
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def train():
    import numpy as np
    from transformers import (
        AutoTokenizer,
        AutoModelForSequenceClassification,
        TrainingArguments,
        Trainer,
    )
    from datasets import Dataset
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import accuracy_score, classification_report

    label2id = {"important": 0, "okay": 1, "unwanted": 2}
    id2label = {0: "important", 1: "okay", 2: "unwanted"}

    # ── load training data ────────────────────────────────────────────────────
    data_path = os.path.join(os.path.dirname(__file__), "training_data.jsonl")
    if not os.path.exists(data_path):
        print("❌ training_data.jsonl not found. Run export_training_data.py first.")
        return

    samples = []
    with open(data_path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            s = json.loads(line)
            s["label_id"] = label2id[s["label"]]
            samples.append(s)

    print(f"📊 Loaded {len(samples)} training samples")

    label_counts = {l: sum(1 for s in samples if s["label"] == l) for l in label2id}
    print(f"   Distribution: {label_counts}")

    # ── train/eval split ──────────────────────────────────────────────────────
    test_size = max(0.15, 3 / len(samples))
    train_data, eval_data = train_test_split(
        samples,
        test_size=test_size,
        random_state=42,
        stratify=[s["label"] for s in samples],
    )
    print(f"   Train: {len(train_data)} | Eval: {len(eval_data)}")

    # ── DistilBERT ────────────────────────────────────────────────────────────
    model_name = "distilbert-base-uncased"
    print(f"\n📥 Loading {model_name}...")
    tokenizer = AutoTokenizer.from_pretrained(model_name)

    def make_dataset(data):
        ds = Dataset.from_list([
            {"text": s["text"], "label": s["label_id"]} for s in data
        ])
        return ds.map(
            lambda batch: tokenizer(
                batch["text"],
                truncation=True,
                padding="max_length",
                max_length=256,      # 256 handles long subjects + sender
            ),
            batched=True,
        )

    print("🔄 Tokenizing datasets...")
    train_ds = make_dataset(train_data)
    eval_ds  = make_dataset(eval_data)

    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=3,
        id2label=id2label,
        label2id=label2id,
    )

    # ── metrics ───────────────────────────────────────────────────────────────
    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        preds = np.argmax(logits, axis=1)
        return {"accuracy": accuracy_score(labels, preds)}

    # ── training config ───────────────────────────────────────────────────────
    output_dir = os.path.join(
        os.path.dirname(os.path.dirname(__file__)),
        "email-classifier-final",
    )

    # epoch schedule based on dataset size
    n = len(samples)
    if n < 500:
        epochs = 10
    elif n < 2000:
        epochs = 5
    else:
        epochs = 4   # 13k samples → 4 epochs is plenty

    print(f"\n⚙️  Training config:")
    print(f"   Model   : {model_name}")
    print(f"   Epochs  : {epochs}")
    print(f"   Samples : {len(train_data)} train / {len(eval_data)} eval")
    print(f"   Max len : 256 tokens")
    print(f"   Output  : {output_dir}")

    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=16,
        per_device_eval_batch_size=16,
        eval_strategy="epoch",          # fixed: was evaluation_strategy
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="accuracy",
        greater_is_better=True,
        learning_rate=2e-5,
        weight_decay=0.01,
        warmup_ratio=0.1,
        logging_steps=50,
        report_to="none",
        save_total_limit=2,             # keep only best 2 checkpoints
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_ds,
        eval_dataset=eval_ds,
        compute_metrics=compute_metrics,
    )

    # ── train ─────────────────────────────────────────────────────────────────
    print(f"\n🚀 Training DistilBERT for {epochs} epochs...")
    trainer.train()

    # ── save ──────────────────────────────────────────────────────────────────
    trainer.save_model(output_dir)
    tokenizer.save_pretrained(output_dir)
    print(f"\n💾 Model saved to {output_dir}")

    # ── final evaluation ──────────────────────────────────────────────────────
    print("\n📊 Running final evaluation...")
    preds_out = trainer.predict(eval_ds)
    preds  = np.argmax(preds_out.predictions, axis=1)
    labels = preds_out.label_ids

    final_acc = accuracy_score(labels, preds)
    print(f"\n✅ Final accuracy: {final_acc:.1%}")
    print("\nClassification Report:")
    print(classification_report(
        labels, preds,
        target_names=["important", "okay", "unwanted"],
        digits=3,
    ))

    # save accuracy to file for reference
    meta = {
        "model": model_name,
        "accuracy": round(final_acc, 4),
        "samples": len(samples),
        "epochs": epochs,
        "label_distribution": label_counts,
    }
    meta_path = os.path.join(output_dir, "training_meta.json")
    with open(meta_path, "w") as f:
        json.dump(meta, f, indent=2)
    print(f"📝 Training metadata saved to {meta_path}")


if __name__ == "__main__":
    train()