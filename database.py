"""
SQLite database voor het outreach systeem.
Volledig los van het GHL call-notes systeem.
"""

import aiosqlite
from datetime import datetime, timedelta
from config import settings

DB_PATH = settings.db_path


async def init_db() -> None:
    """Maak de tabellen aan als ze nog niet bestaan."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute("""
            CREATE TABLE IF NOT EXISTS leads (
                id               INTEGER PRIMARY KEY AUTOINCREMENT,
                first_name       TEXT,
                last_name        TEXT,
                email            TEXT UNIQUE NOT NULL,
                company_name     TEXT,
                website          TEXT,
                linkedin_url     TEXT,
                linkedin_id      TEXT,
                niche            TEXT,
                source           TEXT,
                status           TEXT DEFAULT 'te_contacteren',
                stage_updated_at TIMESTAMP,
                created_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                notes            TEXT
            )
        """)
        await db.execute("""
            CREATE TABLE IF NOT EXISTS outreach_log (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                lead_id       INTEGER NOT NULL REFERENCES leads(id),
                channel       TEXT NOT NULL,
                template_key  TEXT NOT NULL,
                sent_at       TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                success       INTEGER NOT NULL DEFAULT 1,
                error_message TEXT DEFAULT ''
            )
        """)
        await db.commit()
    print(f"[Database] Tabellen klaar in {DB_PATH}")


async def create_lead(lead: dict) -> int | None:
    """
    Sla een nieuwe lead op. Geeft het ID terug, of None als het emailadres
    al bestaat (duplicaat wordt stilletjes genegeerd).
    """
    try:
        async with aiosqlite.connect(DB_PATH) as db:
            cursor = await db.execute(
                """
                INSERT INTO leads
                    (first_name, last_name, email, company_name, website,
                     linkedin_url, linkedin_id, niche, source)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    lead.get("first_name", ""),
                    lead.get("last_name", ""),
                    lead["email"],
                    lead.get("company_name", ""),
                    lead.get("website", ""),
                    lead.get("linkedin_url", ""),
                    lead.get("linkedin_id", ""),
                    lead.get("niche", ""),
                    lead.get("source", ""),
                ),
            )
            await db.commit()
            return cursor.lastrowid
    except aiosqlite.IntegrityError:
        # Email bestaat al
        return None


async def get_leads_by_status(status: str) -> list[dict]:
    """Haal alle leads op met een bepaalde status."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM leads WHERE status = ? ORDER BY created_at ASC",
            (status,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_leads_ready_for_followup(status: str, delay_days: int) -> list[dict]:
    """
    Haal leads op met de gegeven status waarvan de stage_updated_at
    minimaal delay_days geleden is (klaar voor volgende follow-up).
    """
    cutoff = datetime.utcnow() - timedelta(days=delay_days)
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """
            SELECT * FROM leads
            WHERE status = ?
              AND stage_updated_at IS NOT NULL
              AND stage_updated_at <= ?
            ORDER BY stage_updated_at ASC
            """,
            (status, cutoff.isoformat()),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def update_lead_status(lead_id: int, new_status: str) -> None:
    """Update de status en het tijdstip van de laatste statuswijziging."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            UPDATE leads
            SET status = ?, stage_updated_at = ?
            WHERE id = ?
            """,
            (new_status, datetime.utcnow().isoformat(), lead_id),
        )
        await db.commit()


async def log_outreach(
    lead_id: int,
    channel: str,
    template_key: str,
    success: bool,
    error: str = "",
) -> None:
    """Registreer een verzonden email of LinkedIn actie."""
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT INTO outreach_log (lead_id, channel, template_key, success, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (lead_id, channel, template_key, 1 if success else 0, error),
        )
        await db.commit()


async def get_sent_today() -> int:
    """Aantal succesvolle outreach-acties van vandaag."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            """
            SELECT COUNT(*) FROM outreach_log
            WHERE success = 1
              AND date(sent_at) = date('now')
            """
        ) as cursor:
            row = await cursor.fetchone()
    return row[0] if row else 0


async def get_all_leads(limit: int = 500) -> list[dict]:
    """Haal alle leads op (voor het /leads endpoint)."""
    async with aiosqlite.connect(DB_PATH) as db:
        db.row_factory = aiosqlite.Row
        async with db.execute(
            "SELECT * FROM leads ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
    return [dict(row) for row in rows]


async def get_status_counts() -> dict:
    """Aantal leads per status (voor /stats endpoint)."""
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT status, COUNT(*) as n FROM leads GROUP BY status"
        ) as cursor:
            rows = await cursor.fetchall()
    return {row[0]: row[1] for row in rows}
