import json
import os
import concurrent.futures
from model import call_llm, DistilledEmailClassifier

def _get_classification_prompt():
    prompt = os.environ.get("CLASSIFICATION_PROMPT", "")
    if not prompt:
        try:
            from prompts import CLASSIFICATION_PROMPT
            prompt = CLASSIFICATION_PROMPT
        except ImportError:
            raise RuntimeError(
                "prompts.py not found and CLASSIFICATION_PROMPT env var is not set.\n"
                "Run 'python createprompt.py' to generate your personalized prompt."
            )
    return prompt


def classify_with_llm(subject: str, sender: str, snippet: str) -> dict:
    subject = (subject or "").strip()
    sender  = (sender  or "").strip()
    snippet = (snippet or "").strip()

    full_prompt = (
        _get_classification_prompt()
        + "\n━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + "NOW CLASSIFY THIS EMAIL:\n"
        + "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
        + f"From: {sender.lower()}\n"
        + f"Subject: {subject.lower()}\n"
        + f"Preview: {snippet.lower()}\n"
    )

    raw = call_llm(full_prompt).strip()

    if "```" in raw:
        raw = "\n".join(
            line for line in raw.split("\n")
            if not line.strip().startswith("```")
        ).strip()

    json_line = None
    for line in raw.split("\n"):
        stripped = line.strip()
        if stripped.startswith("{") and stripped.endswith("}"):
            json_line = stripped
            break

    if not json_line:
        try:
            result = json.loads(raw)
            if result.get("category") in ["important", "okay", "unwanted"]:
                return result
        except Exception:
            pass
        return {"category": "okay", "reason": "no json returned"}

    try:
        result = json.loads(json_line)
        if result.get("category") not in ["important", "okay", "unwanted"]:
            result["category"] = "okay"
        return result
    except Exception:
        return {"category": "okay", "reason": f"parse error: {json_line[:80]}"}


def classify_emails_batch(emails: list) -> list:
    if not emails:
        return []

    student_results = DistilledEmailClassifier.classify_batch(emails)

    final_results = [None] * len(emails)
    llm_needed = []

    for i, (email, student_result) in enumerate(zip(emails, student_results)):
        if student_result is not None:
            final_results[i] = {**email, **student_result, "error": None}
        else:
            llm_needed.append((i, email))

    if llm_needed:
        def _classify_one(idx_email):
            idx, email = idx_email
            try:
                result = classify_with_llm(
                    subject=email["subject"],
                    sender=email["sender"],
                    snippet=email["snippet"],
                )
                return idx, {**email, **result, "error": None}
            except Exception as e:
                return idx, {
                    **email,
                    "category": "okay",
                    "reason": f"LLM fallback failed, marked okay: {str(e)[:50]}",
                    "error": str(e),
                }

        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
            for idx, result in executor.map(_classify_one, llm_needed):
                final_results[idx] = result

    return final_results
