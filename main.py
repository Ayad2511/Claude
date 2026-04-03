"""
Gecombineerde server:
  1. GHL Call Notes AI — verwerkt gespreksopnames via webhooks
  2. Outreach Systeem — geautomatiseerde email/LinkedIn outreach voor high-ticket closing

Start met:
    uvicorn main:app --host 0.0.0.0 --port 8000

GHL webhook-URL: https://jouw-server.com/webhook/call-completed
Outreach endpoints: /outreach/now, /scrape/now, /leads, /stats
"""

import io
import csv
from contextlib import asynccontextmanager

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger
from fastapi import FastAPI, Request, HTTPException, BackgroundTasks, UploadFile, File
from fastapi.responses import JSONResponse

import ghl_client
import ai_processor
import slack_reporter
import stage_advancer
import database
import outreach_pipeline
import scraper
from config import settings

# ─────────────────────────────────────────────
# Dagelijkse statistieken (reset na dagrapport)
# ─────────────────────────────────────────────
def _empty_stats() -> dict:
    return {
        "total_webhooks": 0,
        "calls_with_recording": 0,
        "calls_processed": 0,
        "niet_opgenomen": 0,
        "categories": {
            "geen_fit_geen_interesse": 0,
            "icp_geen_fit": 0,
            "icp_geen_interesse": 0,
            "icp_niet_warm": 0,
            "icp_gepland": 0,
        },
        "vsl_bekeken_ja": 0,
        "vsl_bekeken_nee": 0,
        "samenvattingen": [],
    }

daily_stats = _empty_stats()


async def send_and_reset():
    """Stuur het dagrapport naar Slack en reset de tellers."""
    global daily_stats
    await slack_reporter.send_daily_report(daily_stats)
    daily_stats = _empty_stats()
    print("[Scheduler] Stats gereset voor nieuwe dag.")


async def advance_stages_job():
    """Schuif niet-opgenomen leads elke ochtend één dag door."""
    stats = await stage_advancer.advance_not_answered_leads()
    total = sum(stats.values())
    print(f"[Scheduler] Doorschuiven klaar: {total} lead(s) verschoven.")


async def scrape_job_wrapper():
    """Dagelijkse scraper-run (07:00)."""
    print("[Scheduler] Scrape-job gestart")
    stats = await scraper.run_scrape_job()
    print(f"[Scheduler] Scrape-job klaar: {stats}")


async def outreach_job_wrapper():
    """Dagelijkse outreach-run (09:00)."""
    print("[Scheduler] Outreach-job gestart")
    stats = await outreach_pipeline.run_outreach_job()
    print(f"[Scheduler] Outreach-job klaar: {stats}")


# ─────────────────────────────────────────────
# App lifecycle
# ─────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialiseer SQLite database voor outreach systeem
    await database.init_db()

    scheduler = AsyncIOScheduler()

    # GHL: Dagrapport naar Slack
    r_hour, r_min = map(int, settings.daily_report_time.split(":"))
    scheduler.add_job(send_and_reset, CronTrigger(hour=r_hour, minute=r_min))
    print(f"[Scheduler] Dagrapport ingepland om {settings.daily_report_time}")

    # GHL: Ochtend — niet-opgenomen leads doorschuiven
    a_hour, a_min = map(int, settings.daily_advance_time.split(":"))
    scheduler.add_job(advance_stages_job, CronTrigger(hour=a_hour, minute=a_min))
    print(f"[Scheduler] Doorschuiven ingepland om {settings.daily_advance_time}")

    # Outreach: dagelijkse scrape (07:00)
    s_hour, s_min = map(int, settings.scrape_run_time.split(":"))
    scheduler.add_job(scrape_job_wrapper, CronTrigger(hour=s_hour, minute=s_min))
    print(f"[Scheduler] Scraper ingepland om {settings.scrape_run_time}")

    # Outreach: dagelijkse email/LinkedIn run (09:00)
    o_hour, o_min = map(int, settings.outreach_run_time.split(":"))
    scheduler.add_job(outreach_job_wrapper, CronTrigger(hour=o_hour, minute=o_min))
    print(f"[Scheduler] Outreach ingepland om {settings.outreach_run_time}")

    scheduler.start()
    yield
    scheduler.shutdown()


app = FastAPI(title="GHL Call Notes AI + Outreach Systeem", version="2.0.0", lifespan=lifespan)


# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────
@app.get("/health")
async def health():
    return {"status": "ok", "stats_vandaag": daily_stats}


@app.post("/report/now")
async def trigger_report_now():
    """Stuur het dagrapport direct (handig voor testen)."""
    await send_and_reset()
    return {"status": "verstuurd"}


@app.post("/advance/now")
async def trigger_advance_now():
    """Schuif niet-opgenomen leads direct door (handig voor testen)."""
    stats = await stage_advancer.advance_not_answered_leads()
    return {"status": "klaar", "verschoven": stats}


# ─────────────────────────────────────────────
# Outreach endpoints
# ─────────────────────────────────────────────
@app.post("/outreach/now")
async def trigger_outreach_now(background_tasks: BackgroundTasks):
    """Start de outreach pipeline direct (handig voor testen)."""
    background_tasks.add_task(outreach_pipeline.run_outreach_job)
    return {"status": "gestart", "dry_run": settings.outreach_dry_run}


@app.post("/scrape/now")
async def trigger_scrape_now(background_tasks: BackgroundTasks):
    """Start de lead scraper direct (handig voor testen)."""
    background_tasks.add_task(scraper.run_scrape_job)
    return {"status": "gestart"}


@app.post("/leads/import")
async def import_leads_csv(file: UploadFile = File(...)):
    """
    Importeer leads via CSV-bestand.
    Verplichte kolom: email
    Optionele kolommen: first_name, last_name, company_name, website, niche, linkedin_url, linkedin_id, notes

    Voorbeeld CSV:
      email,first_name,last_name,company_name,niche
      jan@bedrijf.nl,Jan,Pietersen,Bedrijf BV,business coaching
    """
    content = await file.read()
    try:
        text = content.decode("utf-8-sig")  # utf-8-sig ondersteunt Excel BOM
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    reader = csv.DictReader(io.StringIO(text))
    if "email" not in (reader.fieldnames or []):
        raise HTTPException(status_code=400, detail="CSV moet een 'email' kolom bevatten")

    nieuw = 0
    duplicaat = 0
    ongeldig = 0

    for row in reader:
        email = row.get("email", "").strip().lower()
        if not email or "@" not in email:
            ongeldig += 1
            continue

        lead = {
            "email": email,
            "first_name": row.get("first_name", "").strip(),
            "last_name": row.get("last_name", "").strip(),
            "company_name": row.get("company_name", "").strip(),
            "website": row.get("website", "").strip(),
            "niche": row.get("niche", "").strip(),
            "linkedin_url": row.get("linkedin_url", "").strip(),
            "linkedin_id": row.get("linkedin_id", "").strip(),
            "notes": row.get("notes", "").strip(),
            "source": "csv",
        }
        new_id = await database.create_lead(lead)
        if new_id:
            nieuw += 1
        else:
            duplicaat += 1

    return {
        "status": "klaar",
        "nieuw": nieuw,
        "duplicaat": duplicaat,
        "ongeldig": ongeldig,
    }


@app.get("/leads")
async def get_leads(limit: int = 200):
    """Overzicht van alle leads met status."""
    leads = await database.get_all_leads(limit=limit)
    return {"totaal": len(leads), "leads": leads}


@app.get("/stats")
async def get_stats():
    """Statistieken: leads per status + outreach van vandaag."""
    status_counts = await database.get_status_counts()
    sent_today = await database.get_sent_today()
    return {
        "outreach_vandaag": sent_today,
        "daglimiet": settings.outreach_daily_max,
        "dry_run": settings.outreach_dry_run,
        "leads_per_status": status_counts,
        "totaal_leads": sum(status_counts.values()),
    }


@app.post("/webhook/call-completed")
async def call_completed_webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Ontvangt GHL webhooks wanneer een gesprek klaar is.
    Verwerking op de achtergrond zodat GHL direct een 200 OK krijgt.
    """
    if settings.webhook_secret:
        signature = request.headers.get("X-GHL-Signature", "")
        if not _verify_signature(await request.body(), signature):
            raise HTTPException(status_code=401, detail="Ongeldige webhook signature")

    payload = await request.json()
    print(f"[Webhook] Volledige payload: {payload}")

    daily_stats["total_webhooks"] += 1
    background_tasks.add_task(process_call, payload)
    return JSONResponse({"status": "ontvangen"})


# ─────────────────────────────────────────────
# Hoofdverwerking
# ─────────────────────────────────────────────
def _is_no_answer(payload: dict, call_status: str) -> bool:
    """Bepaal of een gesprek niet is opgenomen."""
    no_answer_statuses = {"no-answer", "no_answer", "noanswer", "missed", "busy", "failed"}
    if call_status.lower().replace(" ", "") in no_answer_statuses:
        return True
    # GHL kan ook een 'answered' veld sturen
    if payload.get("answered") is False:
        return True
    return False


async def process_call(payload: dict):
    """
    Bij opgenomen gesprek:
      → Transcribeer, analyseer, notitie + pipeline-vakje zetten

    Bij niet opgenomen:
      → Direct naar 'Dag 1 - Niet opgenomen' (als nog niet in een dag-stage)
    """
    global daily_stats
    try:
        conversation_id = (
            payload.get("conversationId")
            or payload.get("conversation_id")
        )
        contact_id = (
            payload.get("contactId")
            or payload.get("contact_id")
            or payload.get("contact", {}).get("id")
        )
        contact_name = (
            payload.get("contactName")
            or payload.get("contact_name")
            or payload.get("full_name")
            or payload.get("contact", {}).get("name", "")
        )
        message_id = payload.get("messageId") or payload.get("message_id")
        recording_url = payload.get("recordingUrl") or payload.get("recording_url")
        call_status = (
            payload.get("callStatus")
            or payload.get("call_status")
            or payload.get("status")
            or ""
        )

        if not contact_id:
            print(f"[Verwerking] Geen contact_id in payload, overslagen")
            return

        print(f"[Verwerking] Contact: {contact_name or contact_id} | Status: {call_status or '?'}")

        # ── Niet opgenomen (expliciete status) ─────────────────
        if _is_no_answer(payload, call_status):
            await _handle_no_answer(contact_id, contact_name)
            daily_stats["niet_opgenomen"] += 1
            return

        # ── Opname zoeken ───────────────────────────────────────
        audio_bytes = None

        # Stap 1: conversations ophalen voor dit contact
        if not conversation_id:
            print(f"[Verwerking] Geen conversation_id in payload, zoek op via API...")
            conversations = await ghl_client.get_contact_recent_conversations(contact_id)
            print(f"[Verwerking] {len(conversations)} gesprek(ken) gevonden via API")
        else:
            conversations = [{"id": conversation_id}]

        # Stap 2: loop door alle berichten en probeer opname te halen
        for conv in conversations:
            conv_id = conv.get("id")
            if not conv_id:
                continue
            msgs = await ghl_client.get_conversation_messages(conv_id)
            msg_types = [m.get("type") for m in msgs]
            print(f"[Verwerking] Gesprek {conv_id}: {len(msgs)} bericht(en), types: {msg_types}")
            for msg in reversed(msgs):
                mid = msg.get("id")
                if not mid:
                    continue
                # Haal volledige berichtdetails op (bevat meer velden dan de lijst)
                details = await ghl_client.get_message_details(mid)

                # Zoek opname-URL in berichtdetails
                inline_url = (
                    details.get("url")
                    or details.get("recordingUrl")
                    or (details.get("meta") or {}).get("url")
                    or (details.get("meta") or {}).get("recordingUrl")
                    or details.get("body") if str(details.get("body", "")).startswith("http") else None
                )
                if inline_url:
                    print(f"[Verwerking] Opname-URL in bericht: {inline_url}")
                    audio_bytes = await ghl_client.download_from_url(inline_url)
                    if audio_bytes:
                        print(f"[Verwerking] Opname gedownload ({len(audio_bytes)} bytes)")
                        break

                # Via recording endpoint proberen
                audio_bytes = await ghl_client.get_call_recording(mid)
                if audio_bytes:
                    print(f"[Verwerking] Opname gevonden via endpoint ({len(audio_bytes)} bytes)")
                    break
            if audio_bytes:
                break

        if not audio_bytes:
            print(f"[Verwerking] Geen opname gevonden → als niet opgenomen behandelen")
            await _handle_no_answer(contact_id, contact_name)
            daily_stats["niet_opgenomen"] += 1
            return

        daily_stats["calls_with_recording"] += 1

        # ── Transcribeer + analyseer ────────────────────────────
        transcript = await ai_processor.transcribe_audio(audio_bytes)
        print(f"[Verwerking] Transcriptie klaar ({len(transcript)} tekens)")

        if not transcript.strip():
            print(f"[Verwerking] Lege transcriptie → als niet opgenomen behandelen")
            await _handle_no_answer(contact_id, contact_name)
            daily_stats["niet_opgenomen"] += 1
            return

        analysis = ai_processor.analyze_transcript(transcript, contact_name)
        print(f"[Verwerking] Categorie: {analysis['categorie']} | VSL: {analysis.get('vsl_bekeken')}")

        note_text = ai_processor.format_note(analysis)
        await ghl_client.add_contact_note(contact_id, note_text)
        await ghl_client.set_contact_pipeline_stage(contact_id, analysis["categorie"])

        # Statistieken
        daily_stats["calls_processed"] += 1
        daily_stats["categories"][analysis["categorie"]] += 1
        if "ja" in analysis.get("vsl_bekeken", "nee"):
            daily_stats["vsl_bekeken_ja"] += 1
        else:
            daily_stats["vsl_bekeken_nee"] += 1
        daily_stats["samenvattingen"].append({
            "categorie": analysis["categorie"],
            "samenvatting": analysis.get("samenvatting", ""),
        })

        print(f"[Verwerking] ✅ Klaar voor gesprek {conversation_id}")

    except Exception as e:
        print(f"[Verwerking] ❌ Fout: {e}")
        import traceback
        traceback.print_exc()


# Stages die aangeven dat de lead al in een follow-up dag zit
NIET_OPGENOMEN_STAGE_IDS = {
    settings.stage_dag1_niet_opgenomen,
    settings.stage_dag2_niet_opgenomen,
    settings.stage_dag3_niet_opgenomen,
    settings.stage_nagebeld_niet_opgenomen,
}


async def _handle_no_answer(contact_id: str, contact_name: str):
    """
    Zet de lead in 'Dag 1 - Niet opgenomen', maar alleen als die
    nog niet al in een niet-opgenomen stage zit (voorkom terugval).
    """
    opportunities = await ghl_client.get_contact_opportunities(contact_id)
    pipeline_opps = [o for o in opportunities if o.get("pipelineId") == settings.ghl_pipeline_id]

    # Als de lead al in een niet-opgenomen stage zit, niet terugzetten naar dag 1
    for opp in pipeline_opps:
        if opp.get("pipelineStageId") in NIET_OPGENOMEN_STAGE_IDS:
            print(f"[Verwerking] {contact_name or contact_id} zit al in niet-opgenomen stage, niet terugzetten")
            return

    await ghl_client.set_contact_pipeline_stage(contact_id, "dag1_niet_opgenomen")
    print(f"[Verwerking] {contact_name or contact_id} → Dag 1 - Niet opgenomen")


def _verify_signature(body: bytes, signature: str) -> bool:
    if not signature:
        return False
    # TODO: implementeer Ed25519 verificatie indien vereist door GHL
    return True
