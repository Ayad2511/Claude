"""
Hulpscript om je GHL pipeline stage IDs op te halen.
Voer dit eenmalig uit:

    python get_pipeline_stages.py
"""

import asyncio
import os
import httpx
from dotenv import load_dotenv

load_dotenv()

GHL_API_KEY = os.getenv("GHL_API_KEY", "")
GHL_LOCATION_ID = os.getenv("GHL_LOCATION_ID", "")

if not GHL_API_KEY or not GHL_LOCATION_ID:
    print("❌ Vul GHL_API_KEY en GHL_LOCATION_ID in je .env bestand in en probeer opnieuw.")
    exit(1)

HEADERS = {
    "Authorization": f"Bearer {GHL_API_KEY}",
    "Version": "2021-07-28",
}


async def main():
    print(f"\n🔍 Pipelines ophalen voor locatie: {GHL_LOCATION_ID}\n")

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            "https://services.leadconnectorhq.com/opportunities/pipelines",
            headers=HEADERS,
            params={"locationId": GHL_LOCATION_ID},
        )

    if resp.status_code != 200:
        print(f"❌ Fout van GHL API: {resp.status_code}")
        print(resp.text)
        return

    data = resp.json()
    pipelines = data.get("pipelines", [])

    if not pipelines:
        print("❌ Geen pipelines gevonden. Controleer je GHL_LOCATION_ID.")
        return

    for pipeline in pipelines:
        print(f"{'='*50}")
        print(f"📊 Pipeline: {pipeline['name']}")
        print(f"   GHL_PIPELINE_ID = {pipeline['id']}")
        print(f"\n   Stages:")
        for stage in pipeline.get("stages", []):
            print(f"\n   Stage naam : {stage['name']}")
            print(f"   Stage ID   : {stage['id']}")

    print(f"\n{'='*50}")
    print("✅ Kopieer de IDs hierboven naar je .env bestand.")


if __name__ == "__main__":
    asyncio.run(main())
