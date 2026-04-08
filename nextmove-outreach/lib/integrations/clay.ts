// Clay API — Lead enrichment
// Documentatie: https://docs.clay.com/api-reference

export interface ClayLead {
  id: string;
  first_name: string | null;
  last_name: string | null;
  email: string | null;
  company_name: string | null;
  instagram_handle: string | null;
  linkedin_url: string | null;
  niche: string | null;
}

interface ClayRowsResponse {
  data: Array<{
    id: string;
    fields: Record<string, unknown>;
  }>;
  nextPageToken?: string;
}

const BASE_URL = 'https://api.clay.com/v1';

function headers() {
  return {
    'Authorization': `Bearer ${process.env.CLAY_API_KEY}`,
    'Content-Type': 'application/json',
  };
}

function mapRow(row: { id: string; fields: Record<string, unknown> }): ClayLead {
  const f = row.fields;
  return {
    id: row.id,
    first_name: (f['First Name'] as string) ?? (f['first_name'] as string) ?? null,
    last_name: (f['Last Name'] as string) ?? (f['last_name'] as string) ?? null,
    email: (f['Email'] as string) ?? (f['email'] as string) ?? null,
    company_name: (f['Company'] as string) ?? (f['company_name'] as string) ?? null,
    instagram_handle: (f['Instagram'] as string) ?? (f['instagram_handle'] as string) ?? null,
    linkedin_url: (f['LinkedIn URL'] as string) ?? (f['linkedin_url'] as string) ?? null,
    niche: (f['Niche'] as string) ?? (f['niche'] as string) ?? null,
  };
}

export async function fetchLeadsFromClay(): Promise<ClayLead[]> {
  const tableId = process.env.CLAY_TABLE_ID;
  if (!process.env.CLAY_API_KEY || !tableId) {
    console.log('[Clay] API key of table ID niet ingesteld, skip.');
    return [];
  }

  const leads: ClayLead[] = [];
  let pageToken: string | undefined;

  do {
    const url = new URL(`${BASE_URL}/tables/${tableId}/rows`);
    url.searchParams.set('limit', '100');
    if (pageToken) url.searchParams.set('pageToken', pageToken);

    const resp = await fetch(url.toString(), { headers: headers() });
    if (!resp.ok) {
      console.error(`[Clay] fetchLeads fout: ${resp.status} ${await resp.text()}`);
      break;
    }

    const data: ClayRowsResponse = await resp.json();
    for (const row of data.data) {
      const lead = mapRow(row);
      if (lead.email) leads.push(lead);
    }
    pageToken = data.nextPageToken;
  } while (pageToken);

  console.log(`[Clay] ${leads.length} leads opgehaald`);
  return leads;
}

export async function enrichLead(email: string): Promise<ClayLead | null> {
  const tableId = process.env.CLAY_TABLE_ID;
  if (!process.env.CLAY_API_KEY || !tableId) return null;

  const url = new URL(`${BASE_URL}/tables/${tableId}/rows`);
  url.searchParams.set('filter[email]', email);
  url.searchParams.set('limit', '1');

  const resp = await fetch(url.toString(), { headers: headers() });
  if (!resp.ok) return null;

  const data: ClayRowsResponse = await resp.json();
  if (!data.data.length) return null;
  return mapRow(data.data[0]);
}
