// Lemlist API — Cold email outreach (max 40/dag)
// Documentatie: https://developer.lemlist.com

export interface LemlistReply {
  id: string;
  campaignId: string;
  leadEmail: string;
  text: string;
  receivedAt: string;
}

export interface LemlistStats {
  contacted: number;
  opened: number;
  clicked: number;
  replied: number;
  unsubscribed: number;
  bounced: number;
}

const BASE_URL = 'https://api.lemlist.com/api';

// Lemlist gebruikt Basic Auth met de API key als wachtwoord (gebruiker leeg)
function authHeader() {
  const token = Buffer.from(`:${process.env.LEMLIST_API_KEY}`).toString('base64');
  return {
    'Authorization': `Basic ${token}`,
    'Content-Type': 'application/json',
  };
}

export async function addLeadToCampaign(
  lead: { email: string; firstName?: string | null; lastName?: string | null; companyName?: string | null },
  campaignId?: string
): Promise<boolean> {
  const cid = campaignId ?? process.env.LEMLIST_CAMPAIGN_ID;
  if (!process.env.LEMLIST_API_KEY || !cid) {
    console.log('[Lemlist] API key of campaign ID niet ingesteld, skip.');
    return false;
  }

  const body = {
    email: lead.email,
    firstName: lead.firstName ?? '',
    lastName: lead.lastName ?? '',
    companyName: lead.companyName ?? '',
  };

  const resp = await fetch(`${BASE_URL}/campaigns/${cid}/leads/${lead.email}`, {
    method: 'POST',
    headers: authHeader(),
    body: JSON.stringify(body),
  });

  if (resp.status === 409) {
    // Lead staat al in de campagne
    return true;
  }

  if (!resp.ok) {
    console.error(`[Lemlist] addLead fout: ${resp.status} ${await resp.text()}`);
    return false;
  }

  return true;
}

export async function removeLeadFromCampaign(email: string, campaignId?: string): Promise<boolean> {
  const cid = campaignId ?? process.env.LEMLIST_CAMPAIGN_ID;
  if (!process.env.LEMLIST_API_KEY || !cid) return false;

  const resp = await fetch(`${BASE_URL}/campaigns/${cid}/leads/${email}`, {
    method: 'DELETE',
    headers: authHeader(),
  });
  return resp.ok;
}

export async function getCampaignStats(campaignId?: string): Promise<LemlistStats | null> {
  const cid = campaignId ?? process.env.LEMLIST_CAMPAIGN_ID;
  if (!process.env.LEMLIST_API_KEY || !cid) return null;

  const resp = await fetch(`${BASE_URL}/campaigns/${cid}/stats`, {
    headers: authHeader(),
  });

  if (!resp.ok) return null;
  return resp.json();
}

export async function getInboxReplies(): Promise<LemlistReply[]> {
  if (!process.env.LEMLIST_API_KEY) return [];

  // Haal activiteit op van de laatste 7 dagen
  const since = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000).toISOString();
  const url = new URL(`${BASE_URL}/activities`);
  url.searchParams.set('type', 'emailsReplied');
  url.searchParams.set('since', since);
  url.searchParams.set('limit', '100');

  const resp = await fetch(url.toString(), { headers: authHeader() });
  if (!resp.ok) {
    console.error(`[Lemlist] getInboxReplies fout: ${resp.status}`);
    return [];
  }

  const data = await resp.json();
  // Normalize naar onze interface
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  return (data as any[]).map((item) => ({
    id: item._id ?? item.id,
    campaignId: item.campaignId,
    leadEmail: item.leadEmail ?? item.email,
    text: item.text ?? '',
    receivedAt: item.createdAt ?? item.receivedAt,
  }));
}
