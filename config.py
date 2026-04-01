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

    class Config:
        env_file = ".env"


settings = Settings()
