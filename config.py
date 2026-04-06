"""
Configuratie via environment variables (.env bestand).
"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # === Anthropic (Claude) ===
    anthropic_api_key: str

    # === OpenAI (Whisper transcriptie) ===
    openai_api_key: str

    # === Go High Level ===
    ghl_api_key: str
    ghl_location_id: str
    ghl_pipeline_id: str

    # Pipeline stage IDs — opgenomen gesprekken
    stage_geen_fit_geen_interesse: str
    stage_icp_geen_fit: str
    stage_icp_geen_interesse: str
    stage_icp_niet_warm: str
    stage_icp_gepland: str

    # Pipeline stage IDs — niet opgenomen (follow-up dagen)
    stage_dag1_niet_opgenomen: str
    stage_dag2_niet_opgenomen: str
    stage_dag3_niet_opgenomen: str
    stage_nagebeld_niet_opgenomen: str

    # === Slack dagrapport ===
    slack_webhook_url: str = ""          # Incoming Webhook URL van je Slack app
    daily_report_time: str = "18:00"     # Tijdstip dagrapport (HH:MM, 24-uurs)
    daily_advance_time: str = "08:00"    # Tijdstip automatisch doorschuiven niet-opgenomen leads

    # === Webhook beveiliging (optioneel) ===
    webhook_secret: str = ""

    # =========================================================
    # === OUTREACH SYSTEEM (los van GHL) ===
    # =========================================================

    # Gmail SMTP (App Password, NIET je gewone wachtwoord)
    # Stap 1: Zet 2-stapsverificatie aan op je Google account
    # Stap 2: Google Account → Beveiliging → App-wachtwoorden → Mail
    gmail_address: str = ""
    gmail_app_password: str = ""

    # Resend API (HTTP email — werkt op Railway, vervangt SMTP)
    resend_api_key: str = ""
    # Reply-To adres (bijv. je Gmail) zodat antwoorden daar binnenkomen
    reply_to_email: str = ""

    # Jouw naam als afzender (bijv. "Ahmed Ayad")
    sender_name: str = ""

    # LinkedIn li_at cookie (browser DevTools → Application → Cookies)
    linkedin_li_at: str = ""

    # Loom video URL en thumbnail (haal thumbnail op via Loom dashboard)
    loom_video_url: str = ""
    loom_thumbnail_url: str = ""

    # Follow-up vertragingen (in dagen)
    followup1_delay_days: int = 3
    followup2_delay_days: int = 7
    followup3_delay_days: int = 14
    followup4_delay_days: int = 21

    # Dagelijkse limieten en planning
    outreach_daily_max: int = 15
    outreach_run_time: str = "09:00"
    scrape_run_time: str = "07:00"

    # Dry-run modus: emails worden samengesteld maar NIET verstuurd
    outreach_dry_run: bool = False

    # Scraper: max nieuwe leads per run
    scrape_max_leads_per_run: int = 30

    # Brave Search API (gratis: 2000 queries/maand, zoekt het hele web)
    # Aanmaken: api.search.brave.com → Free plan → API key kopiëren
    brave_api_key: str = ""

    # Google Custom Search API (backup, niet meer nodig als Brave werkt)
    google_api_key: str = ""
    google_cse_id: str = ""

    # SQLite database pad
    db_path: str = "outreach.db"

    class Config:
        env_file = ".env"


settings = Settings()
