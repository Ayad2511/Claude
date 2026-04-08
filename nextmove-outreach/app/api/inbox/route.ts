import { NextRequest, NextResponse } from 'next/server';
import { getInboxReplies } from '@/lib/integrations/lemlist';
import { query } from '@/lib/db';

// GET /api/inbox — centrale inbox met alle replies
export async function GET(req: NextRequest) {
  const { searchParams } = new URL(req.url);
  const channel = searchParams.get('channel');
  const unreadOnly = searchParams.get('unread') === 'true';
  const limit = Math.min(parseInt(searchParams.get('limit') ?? '50'), 200);

  const conditions: string[] = [];
  const params: unknown[] = [];

  if (channel) {
    params.push(channel);
    conditions.push(`m.channel = $${params.length}`);
  }
  if (unreadOnly) {
    conditions.push('m.read = false');
  }

  const where = conditions.length ? `WHERE ${conditions.join(' AND ')}` : '';
  params.push(limit);

  const messages = await query(
    `SELECT m.*, l.first_name, l.last_name, l.company_name, l.instagram_handle
     FROM inbox_messages m
     LEFT JOIN leads l ON l.id = m.lead_id
     ${where}
     ORDER BY m.received_at DESC
     LIMIT $${params.length}`,
    params
  );

  const [{ unread_count }] = await query<{ unread_count: string }>(
    `SELECT COUNT(*) as unread_count FROM inbox_messages WHERE read = false`
  );

  return NextResponse.json({ messages, unreadCount: parseInt(unread_count) });
}

// POST /api/inbox/sync — pull nieuwe replies van Lemlist
export async function POST() {
  const replies = await getInboxReplies();
  let newMessages = 0;

  for (const reply of replies) {
    // Zoek bijbehorende lead
    const leads = await query<{ id: number }>('SELECT id FROM leads WHERE email = $1', [reply.leadEmail]);
    const leadId = leads[0]?.id ?? null;

    // Sla op als nog niet bekend
    const existing = await query('SELECT id FROM inbox_messages WHERE external_id = $1', [reply.id]);
    if (existing.length) continue;

    await query(
      `INSERT INTO inbox_messages (lead_id, channel, direction, content, sender_email, external_id, received_at)
       VALUES ($1, 'email', 'inbound', $2, $3, $4, $5)`,
      [leadId, reply.text, reply.leadEmail, reply.id, reply.receivedAt]
    );

    // Markeer lead als geantwoord
    if (leadId) {
      await query("UPDATE leads SET status = 'geantwoord', updated_at = NOW() WHERE id = $1", [leadId]);
    }
    newMessages++;
  }

  return NextResponse.json({ message: `${newMessages} nieuwe berichten gesynchroniseerd`, newMessages });
}

// PATCH /api/inbox — markeer berichten als gelezen
export async function PATCH(req: NextRequest) {
  const body = await req.json().catch(() => ({}));
  const { ids, readAll } = body;

  if (readAll) {
    await query('UPDATE inbox_messages SET read = true WHERE read = false');
    return NextResponse.json({ message: 'Alle berichten gemarkeerd als gelezen' });
  }

  if (Array.isArray(ids) && ids.length) {
    await query('UPDATE inbox_messages SET read = true WHERE id = ANY($1)', [ids]);
    return NextResponse.json({ message: `${ids.length} berichten gemarkeerd als gelezen` });
  }

  return NextResponse.json({ error: 'Geef ids of readAll mee' }, { status: 400 });
}
