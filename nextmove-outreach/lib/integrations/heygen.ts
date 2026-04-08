// HeyGen API — Gepersonaliseerde video per prospect
// Documentatie: https://docs.heygen.com/reference

export interface HeyGenVideoStatus {
  videoId: string;
  status: 'pending' | 'processing' | 'completed' | 'failed';
  videoUrl: string | null;
  thumbnailUrl: string | null;
  duration: number | null;
  error: string | null;
}

export interface HeyGenWebhookPayload {
  event_type: string;
  event_data: {
    video_id: string;
    status: string;
    url?: string;
    thumbnail?: string;
    duration?: number;
    error?: string;
  };
}

const BASE_URL = 'https://api.heygen.com';

function headers() {
  return {
    'X-Api-Key': process.env.HEYGEN_API_KEY ?? '',
    'Content-Type': 'application/json',
  };
}

export async function generatePersonalizedVideo(lead: {
  firstName: string | null;
  lastName?: string | null;
  companyName: string | null;
  niche?: string | null;
}): Promise<string | null> {
  if (!process.env.HEYGEN_API_KEY || !process.env.HEYGEN_TEMPLATE_ID) {
    console.log('[HeyGen] API key of template ID niet ingesteld, skip.');
    return null;
  }

  const firstName = lead.firstName ?? 'daar';
  const companyName = lead.companyName ?? 'je bedrijf';

  const body = {
    template_id: process.env.HEYGEN_TEMPLATE_ID,
    title: `Video voor ${firstName} — ${companyName}`,
    variables: {
      first_name: { name: 'first_name', type: 'text', properties: { content: firstName } },
      company_name: { name: 'company_name', type: 'text', properties: { content: companyName } },
      niche: { name: 'niche', type: 'text', properties: { content: lead.niche ?? 'beauty' } },
    },
  };

  const resp = await fetch(`${BASE_URL}/v2/video/generate`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify(body),
  });

  if (!resp.ok) {
    console.error(`[HeyGen] generateVideo fout: ${resp.status} ${await resp.text()}`);
    return null;
  }

  const data = await resp.json();
  return (data as { data?: { video_id?: string } }).data?.video_id ?? null;
}

export async function getVideoStatus(videoId: string): Promise<HeyGenVideoStatus | null> {
  if (!process.env.HEYGEN_API_KEY) return null;

  const resp = await fetch(`${BASE_URL}/v1/video_status.get?video_id=${videoId}`, {
    headers: headers(),
  });

  if (!resp.ok) return null;

  const data = await resp.json();
  const v = (data as { data?: Record<string, unknown> }).data ?? {};

  return {
    videoId,
    status: (v.status as HeyGenVideoStatus['status']) ?? 'pending',
    videoUrl: (v.video_url as string) ?? null,
    thumbnailUrl: (v.thumbnail_url as string) ?? null,
    duration: (v.duration as number) ?? null,
    error: (v.error as string) ?? null,
  };
}

export async function getVideoUrl(videoId: string): Promise<string | null> {
  const status = await getVideoStatus(videoId);
  if (status?.status === 'completed') return status.videoUrl;
  return null;
}

// Verifieer dat het webhook request echt van HeyGen komt
export function verifyWebhookSignature(payload: string, signature: string): boolean {
  const secret = process.env.HEYGEN_WEBHOOK_SECRET;
  if (!secret) return true; // Skip verificatie als geen secret ingesteld

  const crypto = require('crypto') as typeof import('crypto');
  const expected = crypto
    .createHmac('sha256', secret)
    .update(payload)
    .digest('hex');

  return crypto.timingSafeEqual(
    Buffer.from(signature),
    Buffer.from(expected)
  );
}
