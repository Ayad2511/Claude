import { NextRequest, NextResponse } from 'next/server';
import { launchLinkedInConnect } from '@/lib/integrations/phantombuster';
import { query } from '@/lib/db';

const DAILY_LINKEDIN_LIMIT = 15;

async function getTodayLinkedInCount(): Promise<number> {
  const rows = await query<{ count: string }>(
    `SELECT COALESCE(count, 0) as count FROM daily_limits WHERE date = CURRENT_DATE AND channel = 'linkedin'`
  );
  return rows.length ? parseInt(rows[0].count) : 0;
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const maxToday = body.limit ?? DAILY_LINKEDIN_LIMIT;
  const message: string = body.message ?? 'Hoi {{firstName}}, ik zag je merk en wilde even connecten. Groeten!';

  const todayCount = await getTodayLinkedInCount();
  const remaining = Math.max(0, maxToday - todayCount);

  if (remaining === 0) {
    return NextResponse.json({ message: `Dagelijks LinkedIn limiet (${maxToday}) bereikt`, launched: false });
  }

  const leads = await query<{ id: number; first_name: string; linkedin_url: string }>(
    `SELECT id, first_name, linkedin_url FROM leads
     WHERE linkedin_url IS NOT NULL AND status NOT IN ('niet_geinteresseerd')
     AND id NOT IN (
       SELECT lead_id FROM outreach_log WHERE channel = 'linkedin' AND success = true
     )
     ORDER BY created_at ASC LIMIT $1`,
    [remaining]
  );

  if (!leads.length) {
    return NextResponse.json({ message: 'Geen leads met LinkedIn URL beschikbaar', launched: false });
  }

  const inputs = leads.map((l) => ({
    linkedinUrl: l.linkedin_url,
    message: message.replace('{{firstName}}', l.first_name ?? 'daar'),
  }));

  const containerId = await launchLinkedInConnect(inputs);

  if (!containerId) {
    return NextResponse.json({ message: 'Phantombuster launch mislukt', launched: false }, { status: 500 });
  }

  // Log de outreach
  for (const lead of leads) {
    await query(
      `INSERT INTO outreach_log (lead_id, channel, template_key, success, external_id) VALUES ($1, 'linkedin', 'connect', true, $2)`,
      [lead.id, containerId]
    );
  }

  await query(
    `INSERT INTO daily_limits (date, channel, count) VALUES (CURRENT_DATE, 'linkedin', $1)
     ON CONFLICT (date, channel) DO UPDATE SET count = daily_limits.count + $1`,
    [leads.length]
  );

  return NextResponse.json({
    message: `LinkedIn Phantom gestart voor ${leads.length} leads`,
    launched: true,
    containerId,
    leadsCount: leads.length,
  });
}

export async function GET() {
  const todayCount = await getTodayLinkedInCount();
  return NextResponse.json({
    today: { sent: todayCount, limit: DAILY_LINKEDIN_LIMIT, remaining: Math.max(0, DAILY_LINKEDIN_LIMIT - todayCount) },
  });
}
