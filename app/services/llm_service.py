import os
from groq import Groq

# ============================================================
# Environment Variables
# ============================================================

GROQ_API_KEY = os.getenv("GROQ_API_KEY")

if not GROQ_API_KEY:
    raise RuntimeError("GROQ_API_KEY is not configured.")


# ============================================================
# Groq Client
# ============================================================

client = Groq(api_key=GROQ_API_KEY)


# ============================================================
# LLM Service
# ============================================================

def call_llm(system_prompt: str, user_prompt: str) -> str:
    response = client.chat.completions.create(
        model="openai/gpt-oss-20b",
        temperature=0.7,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
    )

    return response.choices[0].message.content