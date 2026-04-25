"""
Interactive prompt generator for InboxGuard.
Uses an LLM (Groq or Ollama) to interview you and generate a personalized prompts.py.
"""

import os
import re
from dotenv import load_dotenv

load_dotenv()

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
SETUP_GUIDE = os.path.join(SCRIPT_DIR, "PROMPT_SETUP.md")
OUTPUT_FILE = os.path.join(SCRIPT_DIR, "prompts.py")


def load_system_prompt():
    with open(SETUP_GUIDE, "r", encoding="utf-8") as f:
        return f.read()


def chat_groq(messages):
    from groq import Groq

    api_key = os.getenv("GROQ_API_KEY")
    if not api_key:
        print("\n❌  GROQ_API_KEY is not set.")
        print("    Add it to your .env file:  GROQ_API_KEY=your_key_here")
        print("    Get a free key at https://console.groq.com\n")
        raise SystemExit(1)
    client = Groq(api_key=api_key)
    resp = client.chat.completions.create(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        messages=messages,
        temperature=0.7,
        max_tokens=4096,
    )
    return resp.choices[0].message.content


def chat(messages):
    return chat_groq(messages)


def extract_prompts_py(text):
    pattern = r'CLASSIFICATION_PROMPT\s*=\s*"""(.*?)"""'
    match = re.search(pattern, text, re.DOTALL)
    if match:
        return f'CLASSIFICATION_PROMPT = """{match.group(1)}"""\n'

    if "CLASSIFICATION_PROMPT" in text:
        start = text.find("CLASSIFICATION_PROMPT")
        code = text[start:]
        code = code.replace("```python", "").replace("```", "").strip()
        if code.endswith("\n"):
            return code
        return code + "\n"

    return None


def main():
    print("=" * 55)
    print("  InboxGuard — Personalized Prompt Setup")
    print("  An AI will interview you about your email habits")
    print("  and generate a custom prompts.py for you.")
    print("=" * 55)

    system_prompt = load_system_prompt()

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": "Hi, I'd like to set up my email classifier. Let's start."},
    ]

    print("\nConnecting to LLM...\n")
    reply = chat(messages)
    messages.append({"role": "assistant", "content": reply})
    print(f"AI: {reply}\n")

    while True:
        user_input = input("You: ").strip()
        if not user_input:
            continue

        if user_input.lower() in ("quit", "exit", "q"):
            print("Exiting without saving.")
            return

        messages.append({"role": "user", "content": user_input})
        reply = chat(messages)
        messages.append({"role": "assistant", "content": reply})
        print(f"\nAI: {reply}\n")

        code = extract_prompts_py(reply)
        if code:
            print("-" * 55)
            print("Detected prompts.py in the response!")
            save = input("Save to prompts.py? (y/n): ").strip().lower()
            if save in ("y", "yes"):
                with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
                    f.write(code)
                print(f"\n✅ Saved to {OUTPUT_FILE}")
                print("   Your email classifier is now personalized!")
                return
            else:
                print("Not saved. Continue the conversation to refine it,")
                print("or type 'quit' to exit.\n")


if __name__ == "__main__":
    main()
