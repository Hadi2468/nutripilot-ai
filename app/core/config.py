import os


# ============================================================
# Environment Variables
# ============================================================

API_TOKEN = os.getenv("API_TOKEN")

if not API_TOKEN:
    raise RuntimeError("API_TOKEN is not configured.")