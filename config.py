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

    # Pipeline stage IDs (kopieer deze uit je GHL pipeline-instellingen)
    stage_geen_fit_geen_interesse: str
    stage_icp_geen_fit: str
    stage_icp_geen_interesse: str
    stage_icp_niet_warm: str
    stage_icp_gepland: str

    # === Webhook beveiliging (optioneel) ===
    webhook_secret: str = ""

    class Config:
        env_file = ".env"


settings = Settings()
