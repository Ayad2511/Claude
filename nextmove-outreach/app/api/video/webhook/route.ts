import { NextRequest, NextResponse } from 'next/server';
import { verifyWebhookSignature, HeyGenWebhookPayload } from '@/lib/integrations/heygen';
import { query } from '@/lib/db';

export async function POST(req: NextRequest) {
  const rawBody = await req.text();
  const signature = req.headers.get('x-heygen-signature') ?? '';

  if (!verifyWebhookSignature(rawBody, signature)) {
    return NextResponse.json({ error: 'Ongeldige webhook handtekening' }, { status: 401 });
  }

  let payload: HeyGenWebhookPayload;
  try {
    payload = JSON.parse(rawBody);
  } catch {
    return NextResponse.json({ error: 'Ongeldige JSON' }, { status: 400 });
  }

  if (payload.event_type !== 'avatar_video.success' && payload.event_type !== 'video.completed') {
    // Geen actie nodig voor andere events
    return NextResponse.json({ received: true });
  }

  const { video_id, url, thumbnail } = payload.event_data;

  if (url) {
    await query(
      'UPDATE leads SET heygen_video_url = $1, updated_at = NOW() WHERE heygen_video_id = $2',
      [url, video_id]
    );
    console.log(`[HeyGen webhook] Video ${video_id} klaar: ${url}`);
  }

  if (thumbnail) {
    // Sla thumbnail op als dat nuttig is voor de inbox weergave
    await query(
      `UPDATE leads SET notes = COALESCE(notes, '') || $1 WHERE heygen_video_id = $2`,
      [`thumbnail:${thumbnail}`, video_id]
    );
  }

  return NextResponse.json({ received: true });
}
