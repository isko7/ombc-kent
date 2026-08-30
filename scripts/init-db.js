const { Client } = require('pg');

const connectionString = process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5432/document_app';

async function main() {
  const client = new Client({ connectionString });

  try {
    await client.connect();
    await client.query(`
      CREATE TABLE IF NOT EXISTS recipients (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        label VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
      );
    `);

    await client.query(`
      CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        document_blob BYTEA NOT NULL,
        mime_type VARCHAR(100) DEFAULT 'application/pdf',
        created_at TIMESTAMP DEFAULT NOW()
      );
    `);

    const existing = await client.query('SELECT COUNT(*) AS count FROM recipients');
    if (Number(existing.rows[0].count) === 0) {
      await client.query(
        "INSERT INTO recipients (email, label) VALUES ($1, $2), ($3, $4)",
        ['client@example.com', 'Client principal', 'support@example.com', 'Support']
      );
    }

    console.log('Database initialized successfully.');
  } catch (error) {
    console.error('Database initialization failed:', error.message);
    process.exitCode = 1;
  } finally {
    await client.end();
  }
}

main();
