import { NextResponse } from 'next/server';
import { testConnection } from '@/lib/db';

export async function GET() {
  const dbOk = await testConnection();

  const integrations = {
    clay: !!process.env.CLAY_API_KEY,
    lemlist: !!process.env.LEMLIST_API_KEY,
    phantombuster: !!process.env.PHANTOMBUSTER_API_KEY,
    heygen: !!process.env.HEYGEN_API_KEY,
  };

  const status = dbOk ? 'ok' : 'degraded';

  return NextResponse.json({
    status,
    database: dbOk ? 'connected' : 'disconnected',
    integrations,
    timestamp: new Date().toISOString(),
  }, { status: dbOk ? 200 : 503 });
}
