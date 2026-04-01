# GHL Call Notes AI 🤖📞

Automatische gespreksnotities en lead-categorisering voor Go High Level.

## Wat doet dit?

Na elk opgenomen gesprek in GHL:
1. **Transcribeert** de opname automatisch (via OpenAI Whisper)
2. **Analyseert** het gesprek met Claude AI
3. **Plaatst een notitie** in GHL met samenvatting + transcriptie
4. **Verplaatst de lead** naar het juiste pipeline-vakje:
   - 🔴 Geen fit & geen interesse
   - 🟠 ICP maar geen fit
   - 🟡 ICP met geen interesse
   - 🔵 ICP - niet warm genoeg
   - 🟢 ICP - Gepland/Ingeboekt

---

## Installatie

### 1. Installeer Python dependencies

```bash
pip install -r requirements.txt
```

### 2. Maak een `.env` bestand aan

```bash
cp .env.example .env
```

Vul alle waarden in (zie hieronder).

### 3. Haal je Pipeline Stage IDs op

```bash
python get_pipeline_stages.py
```

Kopieer de juiste Stage IDs naar je `.env` bestand.

### 4. Start de server

```bash
uvicorn main:app --host 0.0.0.0 --port 8000
```

---

## GHL Webhook instellen

1. Ga in GHL naar **Instellingen → Integraties → Webhooks**
2. Voeg een nieuwe webhook toe:
   - **URL**: `https://jouw-server.nl/webhook/call-completed`
   - **Events**: selecteer `Call Status` of `Conversation` events
3. Sla op

> **Tip**: Gebruik [ngrok](https://ngrok.com) tijdens het testen:
> ```bash
> ngrok http 8000
> ```
> Gebruik de gegenereerde HTTPS-URL als webhook endpoint.

---

## Configuratie (`.env`)

| Variabele | Beschrijving |
|---|---|
| `ANTHROPIC_API_KEY` | Claude API key via [console.anthropic.com](https://console.anthropic.com) |
| `OPENAI_API_KEY` | OpenAI API key voor Whisper via [platform.openai.com](https://platform.openai.com) |
| `GHL_API_KEY` | Go High Level API key (Instellingen → API Key) |
| `GHL_LOCATION_ID` | Je GHL locatie/subaccount ID |
| `GHL_PIPELINE_ID` | ID van je pipeline (zie `get_pipeline_stages.py`) |
| `STAGE_*` | Stage IDs van elk pipeline-vakje |

---

## Bestandsoverzicht

| Bestand | Beschrijving |
|---|---|
| `main.py` | FastAPI webhook server |
| `ghl_client.py` | GHL API communicatie |
| `ai_processor.py` | Whisper transcriptie + Claude analyse |
| `config.py` | Configuratie via `.env` |
| `get_pipeline_stages.py` | Hulpscript om Stage IDs op te halen |

---

## Hoe werkt de lead-categorisering?

Claude analyseert de transcriptie en kiest automatisch een categorie:

| Categorie | Wanneer |
|---|---|
| **Geen fit & geen interesse** | Contact voldoet niet aan ICP én heeft geen interesse |
| **ICP maar geen fit** | Wel ICP-profiel, maar verkeerde situatie/budget/timing |
| **ICP met geen interesse** | Wel ICP-profiel, maar nu geen interesse |
| **ICP - niet warm genoeg** | ICP + interesse, maar nog niet klaar voor een afspraak |
| **ICP - Gepland** | ICP + afspraak of concrete vervolgstap ingepland |

---

## Taal van gesprekken aanpassen

Gesprekken worden standaard als **Nederlands** getranscribeerd. Voor andere talen, pas in `ai_processor.py` de `language` parameter aan:

```python
response = await openai_client.audio.transcriptions.create(
    model="whisper-1",
    file=audio_file,
    language="nl",  # Verander naar bijv. "en", "de", "fr"
)
```
