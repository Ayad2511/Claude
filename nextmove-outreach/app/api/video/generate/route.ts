import { NextRequest, NextResponse } from 'next/server';
import { generatePersonalizedVideo } from '@/lib/integrations/heygen';
import { query } from '@/lib/db';

export async function POST(req: NextRequest) {
  const body = await req.json().catch(() => ({}));

  // Optioneel: specifieke lead ID, anders batch voor alle leads zonder video
  const leadId: number | undefined = body.leadId;

  if (leadId) {
    // Genereer voor één lead
    const leads = await query<{
      id: number; first_name: string; last_name: string; company_name: string; niche: string;
    }>('SELECT id, first_name, last_name, company_name, niche FROM leads WHERE id = $1', [leadId]);

    if (!leads.length) {
      return NextResponse.json({ error: 'Lead niet gevonden' }, { status: 404 });
    }

    const lead = leads[0];
    if (!lead) {
      return NextResponse.json({ error: 'Lead niet gevonden' }, { status: 404 });
    }
    const videoId = await generatePersonalizedVideo({
      firstName: lead.first_name,
      lastName: lead.last_name,
      companyName: lead.company_name,
      niche: lead.niche,
    });

    if (!videoId) {
      return NextResponse.json({ error: 'HeyGen video generatie mislukt' }, { status: 500 });
    }

    await query('UPDATE leads SET heygen_video_id = $1, updated_at = NOW() WHERE id = $2', [videoId, leadId]);
    return NextResponse.json({ leadId, videoId, status: 'processing' });
  }

  // Batch: genereer video's voor leads zonder video (max 20 per keer)
  const leads = await query<{
    id: number; first_name: string; last_name: string; company_name: string; niche: string;
  }>(
    `SELECT id, first_name, last_name, company_name, niche FROM leads
     WHERE heygen_video_id IS NULL AND status NOT IN ('niet_geinteresseerd')
     AND email IS NOT NULL
     ORDER BY created_at ASC LIMIT 20`
  );

  const results: Array<{ leadId: number; videoId: string | null }> = [];

  for (const lead of leads) {
    const videoId = await generatePersonalizedVideo({
      firstName: lead.first_name,
      lastName: lead.last_name,
      companyName: lead.company_name,
      niche: lead.niche,
    });
    if (videoId) {
      await query('UPDATE leads SET heygen_video_id = $1, updated_at = NOW() WHERE id = $2', [videoId, lead.id]);
    }
    results.push({ leadId: lead.id, videoId });
  }

  return NextResponse.json({
    message: `${results.filter((r) => r.videoId).length}/${results.length} video's gestart`,
    results,
  });
}
