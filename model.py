import os
import threading
from dotenv import load_dotenv

load_dotenv()

STUDENT_CONFIDENCE_THRESHOLD = 0.70
_lock = threading.Lock()
_groq_client = None


def _get_groq():
    global _groq_client
    if _groq_client is None:
        api_key = os.getenv("GROQ_API_KEY")
        if not api_key:
            return None
        from groq import Groq
        _groq_client = Groq(api_key=api_key)
    return _groq_client


def call_llm(prompt: str) -> str:
    """Call Groq LLM for classification. Raises ConnectionError on failure."""
    groq = _get_groq()
    if groq is not None:
        try:
            resp = groq.chat.completions.create(
                model=os.getenv("GROQ_MODEL", "meta-llama/llama-4-scout-17b-16e-instruct"),
                messages=[{"role": "user", "content": prompt}],
                temperature=0.1,
                max_tokens=100,
            )
            return resp.choices[0].message.content
        except Exception as e:
            raise ConnectionError(f"Groq failed: {e}")

    raise ConnectionError("No Groq API key configured")


class DistilledEmailClassifier:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            with _lock:
                if cls._instance is None:
                    model_path = os.path.join(
                        os.path.dirname(os.path.abspath(__file__)),
                        "email-classifier-final",
                    )
                    if not os.path.exists(model_path):
                        return None
                    import torch
                    from transformers import pipeline
                    device = 0 if torch.cuda.is_available() else -1
                    cls._instance = pipeline(
                        "text-classification",
                        model=model_path,
                        device=device,
                    )
        return cls._instance

    @staticmethod
    def classify(sender: str, subject: str, snippet: str) -> dict | None:
        clf = DistilledEmailClassifier.get_instance()
        if clf is None:
            return None

        text = f"From: {sender}\nSubject: {subject}"
        result = clf(text, truncation=True, max_length=256)[0]

        if result["score"] < STUDENT_CONFIDENCE_THRESHOLD:
            return None

        return {
            "category": result["label"],
            "reason": f"student model (conf: {result['score']:.2f})",
        }

    @staticmethod
    def classify_batch(emails: list) -> list:
        clf = DistilledEmailClassifier.get_instance()
        if clf is None:
            return [None] * len(emails)

        texts = [
            f"From: {e.get('sender', '')}\nSubject: {e.get('subject', '')}"
            for e in emails
        ]

        results = clf(texts, batch_size=32, truncation=True, max_length=256)

        output = []
        for result in results:
            if result["score"] < STUDENT_CONFIDENCE_THRESHOLD:
                output.append(None)
            else:
                output.append({
                    "category": result["label"],
                    "reason": f"student model (conf: {result['score']:.2f})",
                })
        return output
