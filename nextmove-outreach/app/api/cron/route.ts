import { NextRequest, NextResponse } from 'next/server';

// Beveilig de cron endpoint met een geheime header
function isAuthorized(req: NextRequest): boolean {
  const secret = process.env.CRON_SECRET;
  if (!secret) return true; // Dev: geen secret vereist
  return req.headers.get('x-cron-secret') === secret;
}

// POST /api/cron?job=daily_outreach
export async function POST(req: NextRequest) {
  if (!isAuthorized(req)) {
    return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
  }

  const { searchParams } = new URL(req.url);
  const job = searchParams.get('job') ?? 'daily_outreach';

  const baseUrl = process.env.NEXTAUTH_URL ?? 'http://localhost:3000';
  const results: Record<string, unknown> = {};

  if (job === 'sync_leads' || job === 'daily_outreach') {
    // 1. Sync leads van Clay
    const syncResp = await fetch(`${baseUrl}/api/leads/sync`, { method: 'POST' });
    results.sync = await syncResp.json();
  }

  if (job === 'generate_videos' || job === 'daily_outreach') {
    // 2. Genereer HeyGen video's voor nieuwe leads
    const videoResp = await fetch(`${baseUrl}/api/video/generate`, { method: 'POST' });
    results.videos = await videoResp.json();
  }

  if (job === 'email' || job === 'daily_outreach') {
    // 3. Email campagne (40/dag via Lemlist)
    const emailResp = await fetch(`${baseUrl}/api/campaigns/email`, { method: 'POST' });
    results.email = await emailResp.json();
  }

  if (job === 'linkedin' || job === 'daily_outreach') {
    // 4. LinkedIn connect (15/dag via Phantombuster)
    const linkedinResp = await fetch(`${baseUrl}/api/campaigns/linkedin`, { method: 'POST' });
    results.linkedin = await linkedinResp.json();
  }

  if (job === 'instagram' || job === 'daily_outreach') {
    // 5. Instagram DM (7/dag via Phantombuster)
    const igResp = await fetch(`${baseUrl}/api/campaigns/instagram`, { method: 'POST' });
    results.instagram = await igResp.json();
  }

  if (job === 'sync_inbox' || job === 'daily_outreach') {
    // 6. Sync inbox replies van Lemlist
    const inboxResp = await fetch(`${baseUrl}/api/inbox`, { method: 'POST' });
    results.inbox = await inboxResp.json();
  }

  console.log(`[cron] Job '${job}' voltooid:`, JSON.stringify(results));
  return NextResponse.json({ job, results, timestamp: new Date().toISOString() });
}
