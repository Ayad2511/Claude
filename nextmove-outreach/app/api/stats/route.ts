import { NextResponse } from 'next/server';
import { query } from '@/lib/db';

export async function GET() {
  const [statusCounts, todayLimits, recentLog, unreadCount] = await Promise.all([
    query<{ status: string; count: string }>(
      `SELECT status, COUNT(*) as count FROM leads GROUP BY status ORDER BY count DESC`
    ),
    query<{ channel: string; count: string }>(
      `SELECT channel, count FROM daily_limits WHERE date = CURRENT_DATE`
    ),
    query<{ channel: string; success: boolean; count: string }>(
      `SELECT channel, success, COUNT(*) as count
       FROM outreach_log
       WHERE sent_at >= NOW() - INTERVAL '7 days'
       GROUP BY channel, success`
    ),
    query<{ count: string }>(
      `SELECT COUNT(*) as count FROM inbox_messages WHERE read = false`
    ),
  ]);

  const limits = { email: 40, linkedin: 15, instagram: 7 };
  const todayMap: Record<string, number> = {};
  for (const row of todayLimits) todayMap[row.channel] = parseInt(row.count);

  return NextResponse.json({
    leads: {
      byStatus: Object.fromEntries(statusCounts.map((r) => [r.status, parseInt(r.count)])),
      total: statusCounts.reduce((sum, r) => sum + parseInt(r.count), 0),
    },
    today: {
      email: { sent: todayMap['email'] ?? 0, limit: limits.email },
      linkedin: { sent: todayMap['linkedin'] ?? 0, limit: limits.linkedin },
      instagram: { sent: todayMap['instagram'] ?? 0, limit: limits.instagram },
    },
    last7Days: recentLog,
    inbox: { unread: parseInt(unreadCount[0]?.count ?? '0') },
  });
}
