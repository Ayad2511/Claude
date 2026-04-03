"""
Dagelijkse outreach sequencer.

Verwerkt elke ochtend:
  1. Follow-ups: leads die klaar zijn voor de volgende stap (op basis van timing)
  2. Initiële emails: nieuwe leads (status = 'te_contacteren')

Daglimieten worden bewaakt via database.get_sent_today().
Na elke email: 45-90 seconden wachttijd (deliverability).

Lead statussen:
  te_contacteren → email_1 → followup_1 → followup_2 → followup_3 → followup_4
                                                                           ↓
                                                                   niet_geinteresseerd
  geantwoord (handmatig te zetten als iemand reageert)
"""

import asyncio
import random

import database
import email_sender
import email_templates
import linkedin_client
from config import settings

# ─────────────────────────────────────────────────────────────
# FOLLOW-UP KETEN
# (huidige_status, volgende_status, template_key, delay_dagen)
# ─────────────────────────────────────────────────────────────
STATUS_CHAIN = [
    ("email_1",    "followup_1", "followup_1", settings.followup1_delay_days),
    ("followup_1", "followup_2", "followup_2", settings.followup2_delay_days),
    ("followup_2", "followup_3", "followup_3", settings.followup3_delay_days),
    ("followup_3", "followup_4", "followup_4", settings.followup4_delay_days),
]


async def _wait_between_emails() -> None:
    """45-90 seconden willekeurige wachttijd na elke email (spam-preventie)."""
    delay = random.uniform(45, 90)
    print(f"[Pipeline] Wacht {delay:.0f} seconden voor volgende email...")
    await asyncio.sleep(delay)


async def _can_send_more() -> bool:
    """Controleer of dagelijks limiet nog niet bereikt is."""
    sent = await database.get_sent_today()
    if sent >= settings.outreach_daily_max:
        print(f"[Pipeline] Daglimiet bereikt: {sent}/{settings.outreach_daily_max} verstuurd vandaag")
        return False
    return True


# ─────────────────────────────────────────────────────────────
# INITIËLE EMAIL
# ─────────────────────────────────────────────────────────────
async def _send_initial(lead: dict) -> bool:
    """
    Stuur initiële email + LinkedIn connectieverzoek naar een nieuwe lead.
    Bij succes: status → email_1
    """
    lead_id = lead["id"]
    email = lead.get("email", "")

    if not email or email.endswith("@linkedin.placeholder"):
        # Geen geldig emailadres — alleen LinkedIn connectie proberen
        return await _try_linkedin_connection(lead, "initial")

    # AI-gepersonaliseerde email
    content = await email_templates.personalize_email("initial", lead)
    success = await email_sender.send_email(
        to_email=email,
        subject=content["subject"],
        html_body=content["html_body"],
        lead_id=lead_id,
        template_key="initial",
    )

    if success:
        await database.update_lead_status(lead_id, "email_1")
        print(f"[Pipeline] Initiële email verstuurd → {email}")

    # LinkedIn connectieverzoek parallel (onafhankelijk van email succes)
    await _try_linkedin_connection(lead, "connection")

    return success


async def _try_linkedin_connection(lead: dict, template_key: str) -> bool:
    """Stuur een LinkedIn connectieverzoek als linkedin_id beschikbaar is."""
    linkedin_id = lead.get("linkedin_id", "")
    if not linkedin_id:
        return False

    message = await email_templates.personalize_linkedin("connection", lead)
    if not message:
        return False

    success = await linkedin_client.send_connection_request(linkedin_id, message)
    if success:
        await database.log_outreach(lead["id"], "linkedin_connection", template_key, True)
    return success


# ─────────────────────────────────────────────────────────────
# FOLLOW-UP EMAIL
# ─────────────────────────────────────────────────────────────
async def _send_followup(lead: dict, template_key: str, next_status: str) -> bool:
    """
    Stuur een follow-up email (en eventueel LinkedIn DM).
    Bij succes: status → next_status
    """
    lead_id = lead["id"]
    email = lead.get("email", "")

    email_ok = False
    if email and not email.endswith("@linkedin.placeholder"):
        content = await email_templates.personalize_email(template_key, lead)
        email_ok = await email_sender.send_email(
            to_email=email,
            subject=content["subject"],
            html_body=content["html_body"],
            lead_id=lead_id,
            template_key=template_key,
        )

    # LinkedIn DM als de lead ook een linkedin_id heeft (alleen bij FU1)
    if template_key == "followup_1" and lead.get("linkedin_id"):
        li_msg = await email_templates.personalize_linkedin("followup_dm", lead)
        if li_msg:
            li_ok = await linkedin_client.send_message(lead["linkedin_id"], li_msg)
            if li_ok:
                await database.log_outreach(lead_id, "linkedin_message", template_key, True)

    if email_ok:
        await database.update_lead_status(lead_id, next_status)
        print(f"[Pipeline] {template_key} verstuurd → {email} (nieuw status: {next_status})")

    # Laatste follow-up (followup_4): na succes → niet_geinteresseerd
    if next_status == "followup_4" and email_ok:
        # Status blijft followup_4 zodat we weten dat alles verstuurd is
        pass

    return email_ok


# ─────────────────────────────────────────────────────────────
# HOOFD OUTREACH JOB
# ─────────────────────────────────────────────────────────────
async def run_outreach_job() -> dict:
    """
    Voer de dagelijkse outreach uit:
    1. Follow-ups verwerken (tijdgevoelig — altijd eerst)
    2. Nieuwe initiële emails sturen (tot daglimiet)

    Geeft stats terug: {"emails_verstuurd", "linkedin_acties", "fouten"}
    """
    stats = {"emails_verstuurd": 0, "linkedin_acties": 0, "fouten": 0}

    # ── 1. Follow-ups ───────────────────────────────────────
    for current_status, next_status, template_key, delay_days in STATUS_CHAIN:
        if not await _can_send_more():
            break

        leads = await database.get_leads_ready_for_followup(current_status, delay_days)
        print(f"[Pipeline] {len(leads)} lead(s) klaar voor {template_key} (na {delay_days} dagen)")

        for lead in leads:
            if not await _can_send_more():
                break
            try:
                ok = await _send_followup(lead, template_key, next_status)
                if ok:
                    stats["emails_verstuurd"] += 1
                else:
                    stats["fouten"] += 1
            except Exception as e:
                print(f"[Pipeline] Fout bij follow-up voor lead {lead.get('id')}: {e}")
                stats["fouten"] += 1

            await _wait_between_emails()

    # ── 2. Nieuwe leads (initiële email) ────────────────────
    if await _can_send_more():
        new_leads = await database.get_leads_by_status("te_contacteren")
        print(f"[Pipeline] {len(new_leads)} nieuwe lead(s) te contacteren")

        for lead in new_leads:
            if not await _can_send_more():
                break
            try:
                ok = await _send_initial(lead)
                if ok:
                    stats["emails_verstuurd"] += 1
                else:
                    stats["fouten"] += 1
            except Exception as e:
                print(f"[Pipeline] Fout bij initiële email voor lead {lead.get('id')}: {e}")
                stats["fouten"] += 1

            await _wait_between_emails()

    sent_today = await database.get_sent_today()
    print(
        f"[Pipeline] Klaar — emails verstuurd: {stats['emails_verstuurd']}, "
        f"fouten: {stats['fouten']}, "
        f"totaal vandaag: {sent_today}/{settings.outreach_daily_max}"
    )
    return stats
