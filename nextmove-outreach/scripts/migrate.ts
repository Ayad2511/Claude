import { readFileSync } from 'fs';
import { join } from 'path';
import { Pool } from 'pg';

async function migrate() {
  if (!process.env.DATABASE_URL) {
    console.error('DATABASE_URL is niet ingesteld. Maak een .env.local aan op basis van .env.example');
    process.exit(1);
  }

  const pool = new Pool({
    connectionString: process.env.DATABASE_URL,
    ssl: process.env.NODE_ENV === 'production' ? { rejectUnauthorized: false } : false,
  });

  try {
    const schema = readFileSync(join(__dirname, '../lib/schema.sql'), 'utf-8');
    await pool.query(schema);
    console.log('✓ Database schema succesvol aangemaakt/bijgewerkt');
  } catch (err) {
    console.error('Database migratie mislukt:', err);
    process.exit(1);
  } finally {
    await pool.end();
  }
}

migrate();
