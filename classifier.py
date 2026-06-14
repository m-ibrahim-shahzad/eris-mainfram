import re
import os
from openai import OpenAI

# Put your active OpenRouter API key string right here
OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)


def classify_prompt(prompt):
    prompt_lower = prompt.lower().strip()

    # Define the definitive valid categories array
    categories = [
        "CODE", "MATH", "CREATIVE", "SUMMARY", "AGENTIC", "TRANSLATION",
        "SEC_LOGS", "DATA_ANALYSIS", "REASONING_LOGIC", "SYSTEM_ROLE",
        "DESIGN_UX", "BUSINESS_MARKETING", "GENERAL_CONVO", "FACTUAL"
    ]

    # =========================================================================
    # TRACK A: LOCAL REGEX & KEYWORD FAST-PATH (For short, low-complexity prompts)
    # =========================================================================
    # Threshold condition: If prompt is short, evaluate locally to save latency/tokens
    if len(prompt_lower) < 40:
        print(
            f"[Eris Classifier] Short Input Detected ({len(prompt_lower)} chars). Running Local Fast-Path Routing...")

        # Math pattern regex matcher (e.g., "2+2", "x=5")
        if re.search(r'\d+\s*[\+\-\*/\^=]\s*\d+', prompt_lower) or re.search(r'^[xyz\s\d\+\-\*/\^=\(\)]+$', prompt_lower):
            if any(op in prompt_lower for op in ['+', '-', '*', '/', '=', '^']):
                return "MATH"

        # Code block structure regex matcher
        if re.search(r'(def\s+\w+\(|function\s+\w+\(|if\s*\(.*?\)\s*\{|import\s+\w+)', prompt_lower):
            return "CODE"

        # Core categorical matching keyword lists
        code_keywords = ["python", "code", "function", "bug",
                         "error", "script", "program", "api", "html", "css", "json"]
        math_keywords = ["solve", "calculate", "integral",
                         "equation", "math", "compute", "algebra", "fraction"]
        creative_keywords = ["write", "story", "poem",
                             "essay", "create", "imagine", "lyrics", "song"]
        convo_keywords = ["hello", "hi", "hey", "sup", "yo", "greetings",
                          "how are you", "what's up", "haha", "ok", "thanks"]

        for word in code_keywords:
            if word in prompt_lower:
                return "CODE"
        for word in math_keywords:
            if word in prompt_lower:
                return "MATH"
        for word in creative_keywords:
            if word in prompt_lower:
                return "CREATIVE"
        for word in convo_keywords:
            if word in prompt_lower:
                return "GENERAL_CONVO"

        # Keyboard mashes or standalone single-word inputs are highly likely to be conversational gibberish
        if len(prompt_lower) > 0 and " " not in prompt_lower:
            return "GENERAL_CONVO"

        return "FACTUAL"

    # =========================================================================
    # TRACK B: INTELLECTUAL LLM SLOW-PATH (For long, complex semantic prompts)
    # =========================================================================
    print(
        f"[Eris Classifier] Complex Input Detected ({len(prompt_lower)} chars). Escalating to Upstream LLM Intelligence Router...")

    system_instructions = (
        "You are the core intent classification engine for the Eris Orchestration Platform.\n"
        "Your sole job is to analyze the user's input and classify it into exactly ONE of the following categories:\n"
        f"{', '.join(categories)}\n\n"
        "CRITICAL RULES:\n"
        "1. You must ONLY output the exact uppercase category name string.\n"
        "2. Do NOT include periods, quotes, explanations, intro text, or conversational filler.\n"
        "3. Short greetings, gibberish, or casual chit-chat MUST be classified as GENERAL_CONVO.\n"
        "4. Mathematical operations or equations (even plain numbers like 2+2) MUST be classified as MATH."
    )

    try:
        response = client.chat.completions.create(
            model="openrouter/free",
            messages=[
                {"role": "system", "content": system_instructions},
                {"role": "user", "content": f"Classify this input: {prompt}"}
            ],
            extra_headers={
                "HTTP-Referer": "https://localhost:80",
                "X-Title": "Eris Hybrid Classifier",
            },
            temperature=0.0  # Force deterministic matching
        )

        result = response.choices[0].message.content.strip().upper()

        if result in categories:
            return result
        else:
            for cat in categories:
                if cat in result:
                    return cat
            return "FACTUAL"

    except Exception as e:
        print(f"[Classifier Failure]: Upstream node error: {e}")
        return "FACTUAL"


if __name__ == "__main__":
    print("Hybrid Blended Classifier Operational.")
