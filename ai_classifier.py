import json
from model import call_llm

def classify_email(subject: str, sender: str, snippet: str) -> dict:
    """
    Send email details to Groq and get back a classification.
    Returns:
    {
        "category": "important | okay | unwanted",
        "reason": "..." 
    }
    """

    prompt = f"""You are an aggressive email classifier helping clean a cluttered inbox.
        The priority is STORAGE — when in doubt, classify as UNWANTED.

        Email details:
        - Sender: {sender}
        - Subject: {subject}
        - Preview: {snippet}

        Classification rules (be strict):

        "important" → ONLY these:
        - Bank transaction alerts (debit/credit/OTP)
        - Personal emails from real people
        - Account security alerts
        - Bills, receipts, order confirmations
        - Job offers directly addressed to the user
        - Service disruption alerts

        "unwanted" → ALL of these (be aggressive):
        - Any newsletter, even if user subscribed
        - Job board bulk emails (LinkedIn alerts, Naukri, Unstop)
        - Course promotions (Simplilearn, edX, Coursera promos)
        - Bank promotional offers (loans, credit cards, investments)
        - Streak/gamification emails (Chess.com streaks etc.)
        - Any email with discount codes or sale announcements
        - Mutual fund newsletters
        - Marketing from any company

        "okay" → ONLY these:
        - Hackathon announcements
        - Community posts user likely wants (Reddit threads they follow)
        - Direct notifications from platforms user actively uses
        - Emails that don't fit important but are NOT bulk/automated

        When in doubt between okay and unwanted → choose UNWANTED.
        Storage is the priority.

        Respond in this exact JSON format only:
        {{
        "category": "important|okay|unwanted",
        "reason": "one short sentence"
        }}"""

    raw_response = call_llm(prompt).strip()

    try:
        result = json.loads(raw_response)
    except json.JSONDecodeError:
        result = {
            "category": "okay",
            "reason": f"Could not parse AI response, defaulting to 'okay'. Raw response: {raw_response}"
        }
        
    return result
