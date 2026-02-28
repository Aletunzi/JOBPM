#!/usr/bin/env python3
"""Diagnosi Gemini API — stampa la risposta completa con e senza google_search."""
import asyncio, os, json
import httpx
from dotenv import load_dotenv

load_dotenv()

async def test():
    api_key = os.environ.get("GEMINI_API_KEY", "")
    if not api_key:
        print("ERRORE: GEMINI_API_KEY non trovata nel .env")
        return

    endpoint = (
        "https://generativelanguage.googleapis.com/v1beta/models/"
        f"gemini-2.5-flash:generateContent?key={api_key}"
    )
    base_payload = {
        "contents": [{"parts": [{"text": 'Find the career page URL for "Google". Return only the URL.'}]}],
        "generationConfig": {"maxOutputTokens": 300, "temperature": 0.0},
    }

    async with httpx.AsyncClient(timeout=30.0) as client:
        for label, payload in [
            ("SENZA google_search", base_payload),
            ("CON google_search",   {**base_payload, "tools": [{"google_search": {}}]}),
        ]:
            print(f"\n{'='*50}")
            print(f"Test {label}")
            print(f"{'='*50}")
            try:
                r = await client.post(
                    endpoint,
                    headers={"Content-Type": "application/json"},
                    json=payload,
                )
                print(f"HTTP status: {r.status_code}")
                try:
                    data = r.json()
                    print(json.dumps(data, indent=2)[:2000])
                except Exception:
                    print(r.text[:2000])
            except Exception as e:
                print(f"Eccezione: {e}")

asyncio.run(test())
