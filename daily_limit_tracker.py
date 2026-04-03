"""
Dunne wrapper rond database.get_sent_today() voor backwards-compatibiliteit.
De daadwerkelijke limiet-logica zit in outreach_pipeline.py.
"""

import database
from config import settings


async def can_send(max_per_day: int | None = None) -> bool:
    """
    Geeft True terug als het dagelijkse limiet nog niet bereikt is.
    Gebruikt database.get_sent_today() als bron van waarheid.
    """
    limit = max_per_day or settings.outreach_daily_max
    sent = await database.get_sent_today()
    return sent < limit


async def get_sent_today() -> int:
    """Aantal succesvolle outreach-acties van vandaag."""
    return await database.get_sent_today()
