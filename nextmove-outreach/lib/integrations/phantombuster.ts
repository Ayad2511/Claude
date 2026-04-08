// Phantombuster API — LinkedIn (15/dag) + Instagram (7/dag)
// Documentatie: https://api.phantombuster.com/api/v2

export interface PhantomResult {
  agentId: string;
  status: 'running' | 'finished' | 'error';
  output: string | null;
  resultObject: string | null;
}

export interface LinkedInConnectInput {
  linkedinUrl: string;
  message?: string;
}

export interface InstagramDMInput {
  instagramUrl: string;
  message: string;
}

const BASE_URL = 'https://api.phantombuster.com/api/v2';

function headers() {
  return {
    'X-Phantombuster-Key': process.env.PHANTOMBUSTER_API_KEY ?? '',
    'Content-Type': 'application/json',
  };
}

async function launchAgent(agentId: string, argument: Record<string, unknown>): Promise<string | null> {
  const resp = await fetch(`${BASE_URL}/agents/launch`, {
    method: 'POST',
    headers: headers(),
    body: JSON.stringify({ id: agentId, argument }),
  });

  if (!resp.ok) {
    console.error(`[Phantombuster] launchAgent ${agentId} fout: ${resp.status} ${await resp.text()}`);
    return null;
  }

  const data = await resp.json();
  return (data as { containerId?: string }).containerId ?? null;
}

export async function launchLinkedInConnect(leads: LinkedInConnectInput[]): Promise<string | null> {
  const agentId = process.env.PHANTOMBUSTER_LINKEDIN_AGENT_ID;
  if (!process.env.PHANTOMBUSTER_API_KEY || !agentId) {
    console.log('[Phantombuster] LinkedIn agent ID niet ingesteld, skip.');
    return null;
  }

  // Phantombuster LinkedIn Auto Connect verwacht een spreadsheetUrl of een lijst van LinkedIn URLs
  const argument = {
    spreadsheetUrl: leads.map((l) => l.linkedinUrl).join('\n'),
    message: leads[0]?.message ?? '',
    numberOfAddsPerLaunch: Math.min(leads.length, 15),
    onlySecondCircle: false,
  };

  return launchAgent(agentId, argument);
}

export async function launchInstagramDM(leads: InstagramDMInput[]): Promise<string | null> {
  const agentId = process.env.PHANTOMBUSTER_INSTAGRAM_AGENT_ID;
  if (!process.env.PHANTOMBUSTER_API_KEY || !agentId) {
    console.log('[Phantombuster] Instagram agent ID niet ingesteld, skip.');
    return null;
  }

  const argument = {
    spreadsheetUrl: leads.map((l) => l.instagramUrl).join('\n'),
    message: leads[0]?.message ?? '',
    numberOfProfilesPerLaunch: Math.min(leads.length, 7),
    likeLastPublication: true,
    watchStories: true,
  };

  return launchAgent(agentId, argument);
}

export async function getAgentStatus(agentId: string): Promise<PhantomResult | null> {
  if (!process.env.PHANTOMBUSTER_API_KEY) return null;

  const resp = await fetch(`${BASE_URL}/agents/fetch?id=${agentId}`, {
    headers: headers(),
  });

  if (!resp.ok) return null;

  const data = await resp.json();
  return {
    agentId,
    status: (data as { status?: string }).status as PhantomResult['status'] ?? 'error',
    output: (data as { output?: string }).output ?? null,
    resultObject: (data as { resultObject?: string }).resultObject ?? null,
  };
}

export async function getAgentResults(containerId: string): Promise<Record<string, unknown>[]> {
  if (!process.env.PHANTOMBUSTER_API_KEY) return [];

  const resp = await fetch(`${BASE_URL}/containers/fetch-result-object?id=${containerId}`, {
    headers: headers(),
  });

  if (!resp.ok) return [];

  const text = await resp.text();
  try {
    const parsed = JSON.parse(text);
    return Array.isArray(parsed) ? parsed : [parsed];
  } catch {
    return [];
  }
}
