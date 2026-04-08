import { NextResponse } from 'next/server';
import { fetchLeadsFromClay } from '@/lib/integrations/clay';
import { query } from '@/lib/db';

export async function POST() {
  const leads = await fetchLeadsFromClay();

  if (!leads.length) {
    return NextResponse.json({ message: 'Geen nieuwe leads van Clay', imported: 0 });
  }

  let imported = 0;
  let skipped = 0;

  for (const lead of leads) {
    if (!lead.email) { skipped++; continue; }

    const existing = await query('SELECT id FROM leads WHERE email = $1 OR clay_row_id = $2', [lead.email, lead.id]);
    if (existing.length) { skipped++; continue; }

    await query(
      `INSERT INTO leads (first_name, last_name, email, company_name, instagram_handle, linkedin_url, niche, source, clay_row_id)
       VALUES ($1, $2, $3, $4, $5, $6, $7, 'clay', $8)`,
      [lead.first_name, lead.last_name, lead.email, lead.company_name, lead.instagram_handle, lead.linkedin_url, lead.niche, lead.id]
    );
    imported++;
  }

  console.log(`[sync] ${imported} leads geïmporteerd, ${skipped} overgeslagen`);
  return NextResponse.json({ message: 'Clay sync voltooid', imported, skipped, total: leads.length });
}
