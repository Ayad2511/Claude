import { NextRequest, NextResponse } from 'next/server';
import { addLeadToCampaign } from '@/lib/integrations/lemlist';
import { query } from '@/lib/db';

const DAILY_EMAIL_LIMIT = 40;

async function getTodayEmailCount(): Promise<number> {
  const rows = await query<{ count: string }>(
    `SELECT COALESCE(count, 0) as count FROM daily_limits WHERE date = CURRENT_DATE AND channel = 'email'`
  );
  return rows.length ? parseInt(rows[0].count) : 0;
}

async function incrementEmailCount(amount: number) {
  await query(
    `INSERT INTO daily_limits (date, channel, count) VALUES (CURRENT_DATE, 'email', $1)
     ON CONFLICT (date, channel) DO UPDATE SET count = daily_limits.count + $1`,
    [amount]
  );
}

// POST /api/campaigns/email — handmatig starten, of door cron job
export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const maxToday = body.limit ?? DAILY_EMAIL_LIMIT;

  const todayCount = await getTodayEmailCount();
  const remaining = Math.max(0, maxToday - todayCount);

  if (remaining === 0) {
    return NextResponse.json({ message: `Dagelijks limiet (${maxToday}) bereikt`, sent: 0 });
  }

  // Haal leads op die nog geen email hebben ontvangen
  const leads = await query<{
    id: number; first_name: string; last_name: string; email: string; company_name: string;
  }>(
    `SELECT id, first_name, last_name, email, company_name FROM leads
     WHERE status = 'te_contacteren' AND email IS NOT NULL
     ORDER BY created_at ASC LIMIT $1`,
    [remaining]
  );

  if (!leads.length) {
    return NextResponse.json({ message: 'Geen leads klaar voor email outreach', sent: 0 });
  }

  let sent = 0;
  const errors: string[] = [];

  for (const lead of leads) {
    const ok = await addLeadToCampaign({
      email: lead.email,
      firstName: lead.first_name,
      lastName: lead.last_name,
      companyName: lead.company_name,
    });

    if (ok) {
      await query(
        `UPDATE leads SET status = 'email_1', updated_at = NOW() WHERE id = $1`,
        [lead.id]
      );
      await query(
        `INSERT INTO outreach_log (lead_id, channel, template_key, success) VALUES ($1, 'email', 'email_1', true)`,
        [lead.id]
      );
      sent++;
    } else {
      errors.push(lead.email);
      await query(
        `INSERT INTO outreach_log (lead_id, channel, template_key, success, error_message) VALUES ($1, 'email', 'email_1', false, 'Lemlist fout')`,
        [lead.id]
      );
    }
  }

  if (sent > 0) await incrementEmailCount(sent);

  return NextResponse.json({
    message: `${sent} emails toegevoegd aan Lemlist campagne`,
    sent,
    errors: errors.length ? errors : undefined,
  });
}

// GET /api/campaigns/email — statistieken
export async function GET() {
  const { getCampaignStats } = await import('@/lib/integrations/lemlist');
  const stats = await getCampaignStats();
  const todayCount = await getTodayEmailCount();

  return NextResponse.json({
    today: { sent: todayCount, limit: DAILY_EMAIL_LIMIT, remaining: Math.max(0, DAILY_EMAIL_LIMIT - todayCount) },
    campaign: stats,
  });
}
