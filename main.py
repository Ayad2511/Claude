"""
Webhook server voor automatische GHL gespreksnotities.

Start met:
    uvicorn main:app --host 0.0.0.0 --port 8000

Stel de volgende webhook-URL in GHL in:
    https://jouw-server.com/webhook/call-completed
"""

import asyncio
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

import ghl_client
import ai_processor
from config import settings

app = FastAPI(title="GHL Call Notes AI", version="1.0.0")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/webhook/call-completed")
async def call_completed_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Ontvangt GHL webhooks wanneer een gesprek klaar is.
    Verwerking gebeurt op de achtergrond zodat GHL direct een 200 OK krijgt.
    """
    # Optioneel: webhook signature verificatie
    if settings.webhook_secret:
        signature = request.headers.get("X-GHL-Signature", "")
        if not _verify_signature(await request.body(), signature):
            raise HTTPException(status_code=401, detail="Ongeldige webhook signature")

    payload = await request.json()
    print(f"[Webhook] Ontvangen: {payload.get('type', 'onbekend')}")

    # GHL stuurt verschillende event-types; wij willen alleen gesprekken
    event_type = payload.get("type", "")
    if "call" not in event_type.lower() and "conversation" not in event_type.lower():
        return JSONResponse({"status": "genegeerd", "reden": f"Event type: {event_type}"})

    background_tasks.add_task(process_call, payload)
    return JSONResponse({"status": "ontvangen", "bericht": "Verwerking gestart op achtergrond"})


async def process_call(payload: dict):
    """
    Hoofdverwerking (draait op de achtergrond):
    1. Haal gespreksdata op uit webhook
    2. Download de opname
    3. Transcribeer met Whisper
    4. Analyseer met Claude
    5. Voeg notitie toe in GHL
    6. Zet contact in juist pipeline-vakje
    """
    try:
        # Haal benodigde IDs op uit het webhook payload
        # GHL kan het payload op meerdere manieren sturen afhankelijk van de webhook versie
        conversation_id = (
            payload.get("conversationId")
            or payload.get("conversation_id")
            or payload.get("id")
        )
        contact_id = (
            payload.get("contactId")
            or payload.get("contact_id")
            or payload.get("contact", {}).get("id")
        )
        contact_name = (
            payload.get("contactName")
            or payload.get("contact_name")
            or payload.get("contact", {}).get("name", "")
        )
        message_id = payload.get("messageId") or payload.get("message_id")

        # Sommige webhooks bevatten de recording URL direct
        recording_url = payload.get("recordingUrl") or payload.get("recording_url")

        if not conversation_id or not contact_id:
            print(f"[Verwerking] Ontbrekende conversation_id of contact_id in payload: {payload}")
            return

        print(f"[Verwerking] Gesprek {conversation_id} voor contact {contact_id} ({contact_name})")

        # Stap 1: Haal opname-URL op als die niet al in het webhook zit
        if not recording_url:
            if not message_id:
                # Zoek het gespreksbericht op
                messages = await ghl_client.get_conversation_messages(conversation_id)
                call_messages = [m for m in messages if m.get("type") in ("TYPE_CALL", "Call", "call")]
                if not call_messages:
                    print(f"[Verwerking] Geen gespreksberichten gevonden voor {conversation_id}")
                    return
                message_id = call_messages[-1]["id"]

            recording_url = await ghl_client.get_call_recording_url(conversation_id, message_id)

        if not recording_url:
            print(f"[Verwerking] Geen opname gevonden voor gesprek {conversation_id}")
            return

        print(f"[Verwerking] Opname gevonden: {recording_url[:60]}...")

        # Stap 2: Download de opname
        audio_bytes = await ghl_client.download_recording(recording_url)
        print(f"[Verwerking] Opname gedownload ({len(audio_bytes)} bytes)")

        # Stap 3: Transcribeer met Whisper
        transcript = await ai_processor.transcribe_audio(audio_bytes)
        print(f"[Verwerking] Transcriptie klaar ({len(transcript)} tekens)")

        if not transcript.strip():
            print(f"[Verwerking] Lege transcriptie voor gesprek {conversation_id}")
            return

        # Stap 4: Analyseer met Claude
        analysis = ai_processor.analyze_transcript(transcript, contact_name)
        print(f"[Verwerking] Analyse klaar: categorie = {analysis['categorie']}")

        # Stap 5: Formatteer en voeg notitie toe in GHL
        note_text = ai_processor.format_note(analysis, transcript)
        await ghl_client.add_contact_note(contact_id, note_text)
        print(f"[Verwerking] Notitie toegevoegd voor contact {contact_id}")

        # Stap 6: Zet contact in juist pipeline-vakje
        await ghl_client.set_contact_pipeline_stage(contact_id, analysis["categorie"])
        print(f"[Verwerking] Pipeline geüpdatet: {analysis['categorie']}")
        print(f"[Verwerking] ✅ Klaar voor gesprek {conversation_id}")

    except Exception as e:
        print(f"[Verwerking] ❌ Fout bij verwerken van gesprek: {e}")
        import traceback
        traceback.print_exc()


def _verify_signature(body: bytes, signature: str) -> bool:
    """Verifieer de GHL webhook signature (Ed25519)."""
    if not signature:
        return False
    # TODO: implementeer Ed25519 verificatie als GHL dit vereist
    # Zie: https://marketplace.gohighlevel.com/docs/webhook/WebhookIntegrationGuide
    return True
