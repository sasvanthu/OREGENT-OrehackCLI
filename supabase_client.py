"""
supabase_client.py
Place at: OreHack/evaluation_engine1/supabase_client.py

Initializes a single shared Supabase client using the SERVICE_ROLE_KEY.
Service role bypasses Row Level Security — required for worker writes.

Required in .env at project root:
  SUPABASE_URL              = https://xxxx.supabase.co
  SUPABASE_SERVICE_ROLE_KEY = eyJ...   (NOT the anon key)
"""

import os
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv(r"C:\\Users\\SRISAYEE\\Desktop\\Sai\\Coding\\OreHack\\Frontend\\OREHACK\\.env")

def get_supabase_client() -> Client:
    url = os.environ.get("VITE_SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url:
        raise EnvironmentError(
            "SUPABASE_URL not set. Add to .env: SUPABASE_URL=https://xxxx.supabase.co"
        )
    if not key:
        raise EnvironmentError(
            "SUPABASE_SERVICE_ROLE_KEY not set. Add to .env. Use service_role key, NOT anon key."
        )

    return create_client(url, key)


# Singleton — imported directly by worker.py
supabase: Client = get_supabase_client()
