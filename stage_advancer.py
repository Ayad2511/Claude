"""
Dagelijks doorschuiven van niet-opgenomen leads:
  Dag 1 → Dag 2 → Dag 3 → Nagebeld - Niet opgenomen

Wordt elke ochtend automatisch uitgevoerd.
"""

import ghl_client
from config import settings


# Volgorde van doorschuiven: van → naar
ADVANCE_CHAIN = [
    ("dag3_niet_opgenomen", "nagebeld_niet_opgenomen"),
    ("dag2_niet_opgenomen", "dag3_niet_opgenomen"),
    ("dag1_niet_opgenomen", "dag2_niet_opgenomen"),
]

STAGE_ID_MAP = {
    "dag1_niet_opgenomen":    lambda: settings.stage_dag1_niet_opgenomen,
    "dag2_niet_opgenomen":    lambda: settings.stage_dag2_niet_opgenomen,
    "dag3_niet_opgenomen":    lambda: settings.stage_dag3_niet_opgenomen,
    "nagebeld_niet_opgenomen": lambda: settings.stage_nagebeld_niet_opgenomen,
}


async def advance_not_answered_leads() -> dict:
    """
    Schuift alle leads in niet-opgenomen stages één dag door.
    Verwerkt van achteren naar voren zodat leads niet dubbel worden verschoven.

    Geeft statistieken terug over hoeveel leads zijn verschoven.
    """
    stats = {}
    print("[Advancer] Start dagelijks doorschuiven niet-opgenomen leads...")

    for from_key, to_key in ADVANCE_CHAIN:
        from_stage_id = STAGE_ID_MAP[from_key]()
        to_stage_id = STAGE_ID_MAP[to_key]()

        opportunities = await ghl_client.get_opportunities_in_stage(from_stage_id)
        count = len(opportunities)
        stats[f"{from_key} → {to_key}"] = count

        if count == 0:
            print(f"[Advancer] {from_key}: geen leads om te verschuiven")
            continue

        print(f"[Advancer] {from_key} → {to_key}: {count} lead(s) verschuiven...")

        for opp in opportunities:
            try:
                await ghl_client.update_opportunity_stage(
                    opp["id"], settings.ghl_pipeline_id, to_stage_id
                )
            except Exception as e:
                print(f"[Advancer] ❌ Fout bij opportunity {opp['id']}: {e}")

        print(f"[Advancer] ✅ {count} lead(s) verschoven: {from_key} → {to_key}")

    print("[Advancer] Doorschuiven klaar.")
    return stats
