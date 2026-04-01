"""
Hulpscript om je GHL pipeline stage IDs op te halen.
Voer dit eenmalig uit na het instellen van je .env bestand:

    python get_pipeline_stages.py
"""

import asyncio
import httpx
from config import settings


async def main():
    headers = {
        "Authorization": f"Bearer {settings.ghl_api_key}",
        "Version": "2021-07-28",
    }

    print("🔍 Haal pipelines op voor locatie:", settings.ghl_location_id)

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"https://services.leadconnectorhq.com/opportunities/pipelines",
            headers=headers,
            params={"locationId": settings.ghl_location_id},
        )
        resp.raise_for_status()
        data = resp.json()

    pipelines = data.get("pipelines", [])
    if not pipelines:
        print("❌ Geen pipelines gevonden. Controleer je GHL_LOCATION_ID.")
        return

    for pipeline in pipelines:
        print(f"\n📊 Pipeline: {pipeline['name']}")
        print(f"   ID: {pipeline['id']}")
        print("   Stages:")
        for stage in pipeline.get("stages", []):
            print(f"     - {stage['name']}")
            print(f"       ID: {stage['id']}")


if __name__ == "__main__":
    asyncio.run(main())
