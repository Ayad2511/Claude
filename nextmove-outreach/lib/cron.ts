// Cron job scheduler — wordt gestart door server.ts bij app opstart
// Gebruikt node-cron (UTC tijden; Nederland = UTC+1 in winter, UTC+2 in zomer)
//
// Schema:
//  08:00 NL → Clay sync + HeyGen video generatie
//  09:00 NL → Email outreach (40/dag via Lemlist)
//  10:00 NL → LinkedIn connects (15/dag via Phantombuster)
//  11:00 NL → Instagram DM's (7/dag via Phantombuster)
//  18:00 NL → Inbox sync (Lemlist replies ophalen)

import cron from 'node-cron';

let started = false;

export function startCronJobs() {
  if (started) return;
  started = true;

  const baseUrl = process.env.NEXTAUTH_URL ?? 'http://localhost:3000';

  async function triggerJob(job: string) {
    try {
      const resp = await fetch(`${baseUrl}/api/cron?job=${job}`, {
        method: 'POST',
        headers: {
          'x-cron-secret': process.env.CRON_SECRET ?? '',
        },
      });
      if (!resp.ok) {
        console.error(`[cron] Job '${job}' mislukt: ${resp.status}`);
      }
    } catch (err) {
      console.error(`[cron] Job '${job}' fout:`, err);
    }
  }

  // 08:00 NL (07:00 UTC) — Clay sync + video generatie
  cron.schedule('0 7 * * *', () => triggerJob('sync_leads'), { timezone: 'UTC' });
  cron.schedule('5 7 * * *', () => triggerJob('generate_videos'), { timezone: 'UTC' });

  // 09:00 NL (08:00 UTC) — Email
  cron.schedule('0 8 * * 1-5', () => triggerJob('email'), { timezone: 'UTC' });

  // 10:00 NL (09:00 UTC) — LinkedIn
  cron.schedule('0 9 * * 1-5', () => triggerJob('linkedin'), { timezone: 'UTC' });

  // 11:00 NL (10:00 UTC) — Instagram
  cron.schedule('0 10 * * 1-5', () => triggerJob('instagram'), { timezone: 'UTC' });

  // 18:00 NL (17:00 UTC) — Inbox sync
  cron.schedule('0 17 * * *', () => triggerJob('sync_inbox'), { timezone: 'UTC' });

  console.log('[cron] Jobs geregistreerd: sync(07:00), email(08:00), linkedin(09:00), instagram(10:00), inbox(17:00) UTC — ma t/m vr');
}
