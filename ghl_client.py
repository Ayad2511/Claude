"""
Go High Level API client.
Handles: recording download, notes toevoegen, pipeline stage updaten.
"""

import httpx
from config import settings

GHL_BASE = "https://services.leadconnectorhq.com"
HEADERS = {
    "Authorization": f"Bearer {settings.ghl_api_key}",
    "Version": "2021-07-28",
    "Content-Type": "application/json",
}


async def get_conversation_messages(conversation_id: str) -> list[dict]:
    """Haal alle berichten op van een gesprek."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GHL_BASE}/conversations/{conversation_id}/messages",
            headers=HEADERS,
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("messages", {}).get("messages", [])


async def get_call_recording_url(conversation_id: str, message_id: str) -> str | None:
    """Haal de opname-URL op voor een specifiek gespreksbericht."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GHL_BASE}/conversations/messages/{message_id}/locations/{settings.ghl_location_id}/recording",
            headers=HEADERS,
        )
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        return data.get("url")


async def download_recording(url: str) -> bytes:
    """Download het audiobestand van de opname-URL."""
    async with httpx.AsyncClient(timeout=120, follow_redirects=True) as client:
        resp = await client.get(url, headers={"Authorization": f"Bearer {settings.ghl_api_key}"})
        resp.raise_for_status()
        return resp.content


async def add_contact_note(contact_id: str, note_body: str) -> dict:
    """Voeg een notitie toe aan het contact in GHL."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GHL_BASE}/contacts/{contact_id}/notes",
            headers=HEADERS,
            json={"body": note_body},
        )
        resp.raise_for_status()
        return resp.json()


async def get_contact_opportunities(contact_id: str) -> list[dict]:
    """Haal alle opportunities (pipeline entries) op voor een contact."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GHL_BASE}/opportunities/search",
            headers=HEADERS,
            params={
                "location_id": settings.ghl_location_id,
                "contact_id": contact_id,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("opportunities", [])


async def get_contact_recent_conversations(contact_id: str) -> list[dict]:
    """Haal recente gesprekken op voor een contact via de search API."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(
            f"{GHL_BASE}/conversations/search",
            headers=HEADERS,
            params={
                "locationId": settings.ghl_location_id,
                "contactId": contact_id,
                "limit": 5,
            },
        )
        resp.raise_for_status()
        data = resp.json()
        return data.get("conversations", [])


(contact_id: str, pipeline_id: str, stage_id: str, name: str) -> dict:
    """Maak een nieuwe opportunity aan als die nog niet bestaat."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{GHL_BASE}/opportunities/",
            headers=HEADERS,
            json={
                "pipelineId": pipeline_id,
                "locationId": settings.ghl_location_id,
                "name": name,
                "pipelineStageId": stage_id,
                "contactId": contact_id,
                "status": "open",
            },
        )
        resp.raise_for_status()
        return resp.json()


async def update_opportunity_stage(opportunity_id: str, pipeline_id: str, stage_id: str) -> dict:
    """Verplaats een opportunity naar een ander stage (vakje)."""
    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.put(
            f"{GHL_BASE}/opportunities/{opportunity_id}",
            headers=HEADERS,
            json={
                "pipelineId": pipeline_id,
                "pipelineStageId": stage_id,
            },
        )
        resp.raise_for_status()
        return resp.json()


async def get_opportunities_in_stage(stage_id: str) -> list[dict]:
    """Haal alle opportunities op die in een bepaald stage zitten."""
    results = []
    page = 1
    async with httpx.AsyncClient(timeout=30) as client:
        while True:
            resp = await client.get(
                f"{GHL_BASE}/opportunities/search",
                headers=HEADERS,
                params={
                    "location_id": settings.ghl_location_id,
                    "pipeline_id": settings.ghl_pipeline_id,
                    "pipeline_stage_id": stage_id,
                    "page": page,
                    "limit": 100,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            opps = data.get("opportunities", [])
            results.extend(opps)
            if len(opps) < 100:
                break
            page += 1
    return results


async def set_contact_pipeline_stage(contact_id: str, category: str) -> dict | None:
    """
    Zet het contact in het juiste GHL pipeline-vakje op basis van de AI-categorie.

    Categorieën:
      - geen_fit_geen_interesse
      - icp_geen_fit
      - icp_geen_interesse
      - icp_niet_warm
      - icp_gepland
    """
    stage_map = {
        # Opgenomen gesprekken
        "geen_fit_geen_interesse": settings.stage_geen_fit_geen_interesse,
        "icp_geen_fit": settings.stage_icp_geen_fit,
        "icp_geen_interesse": settings.stage_icp_geen_interesse,
        "icp_niet_warm": settings.stage_icp_niet_warm,
        "icp_gepland": settings.stage_icp_gepland,
        # Niet opgenomen
        "dag1_niet_opgenomen": settings.stage_dag1_niet_opgenomen,
        "dag2_niet_opgenomen": settings.stage_dag2_niet_opgenomen,
        "dag3_niet_opgenomen": settings.stage_dag3_niet_opgenomen,
        "nagebeld_niet_opgenomen": settings.stage_nagebeld_niet_opgenomen,
    }

    stage_id = stage_map.get(category)
    if not stage_id:
        print(f"[GHL] Onbekende categorie: {category}, pipeline niet geüpdatet.")
        return None

    # Controleer bestaande opportunities
    opportunities = await get_contact_opportunities(contact_id)

    pipeline_opps = [o for o in opportunities if o.get("pipelineId") == settings.ghl_pipeline_id]

    if pipeline_opps:
        # Update de eerste bestaande opportunity
        opp = pipeline_opps[0]
        result = await update_opportunity_stage(opp["id"], settings.ghl_pipeline_id, stage_id)
        print(f"[GHL] Opportunity {opp['id']} verplaatst naar stage: {category}")
        return result
    else:
        # Maak een nieuwe opportunity aan
        result = await create_opportunity(
            contact_id=contact_id,
            pipeline_id=settings.ghl_pipeline_id,
            stage_id=stage_id,
            name=f"Gesprek - {contact_id}",
        )
        print(f"[GHL] Nieuwe opportunity aangemaakt voor contact {contact_id}, stage: {category}")
        return result
