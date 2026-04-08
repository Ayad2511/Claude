import { NextRequest, NextResponse } from 'next/server';
import { launchInstagramDM } from '@/lib/integrations/phantombuster';
import { query } from '@/lib/db';

const DAILY_INSTAGRAM_LIMIT = 7;

async function getTodayInstagramCount(): Promise<number> {
  const rows = await query<{ count: string }>(
    `SELECT COALESCE(count, 0) as count FROM daily_limits WHERE date = CURRENT_DATE AND channel = 'instagram'`
  );
  return rows.length ? parseInt(rows[0].count) : 0;
}

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const maxToday = body.limit ?? DAILY_INSTAGRAM_LIMIT;
  const message: string = body.message ?? 'Hey {{firstName}}! Ik zag je account en vond je content echt mooi 🙌 Ik werk met beauty brand eigenaren — mag ik je iets sturen?';

  const todayCount = await getTodayInstagramCount();
  const remaining = Math.max(0, maxToday - todayCount);

  if (remaining === 0) {
    return NextResponse.json({ message: `Dagelijks Instagram limiet (${maxToday}) bereikt`, launched: false });
  }

  const leads = await query<{ id: number; first_name: string; instagram_handle: string }>(
    `SELECT id, first_name, instagram_handle FROM leads
     WHERE instagram_handle IS NOT NULL AND status NOT IN ('niet_geinteresseerd')
     AND id NOT IN (
       SELECT lead_id FROM outreach_log WHERE channel = 'instagram' AND success = true
     )
     ORDER BY created_at ASC LIMIT $1`,
    [remaining]
  );

  if (!leads.length) {
    return NextResponse.json({ message: 'Geen leads met Instagram handle beschikbaar', launched: false });
  }

  const inputs = leads.map((l) => {
    const handle = l.instagram_handle.replace('@', '');
    return {
      instagramUrl: `https://www.instagram.com/${handle}/`,
      message: message.replace('{{firstName}}', l.first_name ?? 'hey'),
    };
  });

  const containerId = await launchInstagramDM(inputs);

  if (!containerId) {
    return NextResponse.json({ message: 'Phantombuster Instagram launch mislukt', launched: false }, { status: 500 });
  }

  for (const lead of leads) {
    await query(
      `INSERT INTO outreach_log (lead_id, channel, template_key, success, external_id) VALUES ($1, 'instagram', 'dm_1', true, $2)`,
      [lead.id, containerId]
    );
  }

  await query(
    `INSERT INTO daily_limits (date, channel, count) VALUES (CURRENT_DATE, 'instagram', $1)
     ON CONFLICT (date, channel) DO UPDATE SET count = daily_limits.count + $1`,
    [leads.length]
  );

  return NextResponse.json({
    message: `Instagram Phantom gestart voor ${leads.length} leads (like + story + DM)`,
    launched: true,
    containerId,
    leadsCount: leads.length,
  });
}

export async function GET() {
  const todayCount = await getTodayInstagramCount();
  return NextResponse.json({
    today: { sent: todayCount, limit: DAILY_INSTAGRAM_LIMIT, remaining: Math.max(0, DAILY_INSTAGRAM_LIMIT - todayCount) },
  });
}
