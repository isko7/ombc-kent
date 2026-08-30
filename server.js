const express = require('express');
const path = require('path');
const fs = require('fs');
const multer = require('multer');
const nodemailer = require('nodemailer');
const handlebars = require('handlebars');
const { Pool } = require('pg');
const puppeteer = require('puppeteer');

const app = express();
const PORT = process.env.PORT || 3000;
const uploadDir = path.join(__dirname, 'uploads');
const memoryDocuments = [];
let recipients = [
  { id: 1, email: 'client@example.com', label: 'Client principal' },
  { id: 2, email: 'support@example.com', label: 'Support' }
];

fs.mkdirSync(uploadDir, { recursive: true });
app.use(express.json({ limit: '10mb' }));
app.use(express.urlencoded({ extended: true }));
app.use('/uploads', express.static(uploadDir));
app.use(express.static(path.join(__dirname, 'public')));

const defaultTemplate = `
  <!DOCTYPE html>
  <html>
    <head>
      <meta charset="UTF-8" />
      <style>
        body { font-family: Arial, sans-serif; margin: 40px; color: #1f2937; }
        .header { display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid #e5e7eb; padding-bottom: 20px; margin-bottom: 30px; }
        .title { font-size: 30px; font-weight: 700; }
        .company { font-size: 14px; color: #4b5563; text-align: right; }
        .section { margin-top: 20px; }
        .label { font-weight: 700; color: #111827; }
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { border: 1px solid #d1d5db; padding: 10px; text-align: left; }
        .totals { margin-top: 20px; text-align: right; }
      </style>
    </head>
    <body>
      <div class="header">
        <div>
          <div class="title">Facture</div>
          <div>{{invoiceNumber}}</div>
        </div>
        <div class="company">
          <img src="{{logoUrl}}" alt="Logo" style="max-height: 60px; margin-bottom: 10px;" />
          <div>{{companyName}}</div>
          <div>{{companyAddress}}</div>
        </div>
      </div>

      <div class="section">
        <div><span class="label">Client :</span> {{customerName}}</div>
        <div><span class="label">Email :</span> {{customerEmail}}</div>
        <div><span class="label">Date :</span> {{date}}</div>
      </div>

      <table>
        <thead>
          <tr>
            <th>Service</th>
            <th>Quantité</th>
            <th>Prix unitaire</th>
            <th>Total</th>
          </tr>
        </thead>
        <tbody>
          <tr>
            <td>{{service1}}</td>
            <td>{{qty1}}</td>
            <td>{{unitPrice1}} €</td>
            <td>{{total1}} €</td>
          </tr>
        </tbody>
      </table>

      <div class="totals">
        <div><span class="label">Total HT :</span> {{totalHt}} €</div>
        <div><span class="label">TVA :</span> {{tva}} %</div>
        <div><span class="label">Total TTC :</span> {{totalTtc}} €</div>
      </div>

      <div class="section">
        <div class="label">Notes</div>
        <p>{{notes}}</p>
      </div>
    </body>
  </html>
`;

const upload = multer({ storage: multer.memoryStorage() });
let dbReady = false;
let pool = null;

const connectionString = process.env.DATABASE_URL || 'postgresql://postgres:postgres@localhost:5432/document_app';

async function initDatabase() {
  try {
    pool = new Pool({ connectionString });
    await pool.query('SELECT 1');
    dbReady = true;

    await pool.query(`
      CREATE TABLE IF NOT EXISTS recipients (
        id SERIAL PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        label VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT NOW()
      );
    `);

    await pool.query(`
      CREATE TABLE IF NOT EXISTS documents (
        id SERIAL PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        document_blob BYTEA NOT NULL,
        mime_type VARCHAR(100) DEFAULT 'application/pdf',
        created_at TIMESTAMP DEFAULT NOW()
      );
    `);

    const recipientCheck = await pool.query('SELECT COUNT(*) AS count FROM recipients');
    if (Number(recipientCheck.rows[0].count) === 0) {
      await pool.query(
        "INSERT INTO recipients (email, label) VALUES ($1, $2), ($3, $4)",
        ['client@example.com', 'Client principal', 'support@example.com', 'Support']
      );
    }

    const recipientRows = await pool.query('SELECT * FROM recipients ORDER BY id ASC');
    recipients = recipientRows.rows;
    console.log('PostgreSQL ready.');
  } catch (error) {
    dbReady = false;
    console.warn('PostgreSQL not available; continuing in fallback mode:', error.message);
  }
}

function renderTemplate(templateHtml, data) {
  const compiled = handlebars.compile(templateHtml || defaultTemplate);
  const mergedData = {
    ...data,
    logoUrl: data.logoUrl || '/uploads/logo-placeholder.png',
    invoiceNumber: data.invoiceNumber || 'FAC-001',
    companyName: data.companyName || 'Mon Entreprise',
    companyAddress: data.companyAddress || '12 rue de la Paix, Paris',
    customerName: data.customerName || 'Jean Dupont',
    customerEmail: data.customerEmail || 'jean@exemple.com',
    date: data.date || new Date().toISOString().slice(0, 10),
    service1: data.service1 || 'Service principal',
    qty1: data.qty1 || '1',
    unitPrice1: data.unitPrice1 || '1200',
    total1: data.total1 || '1200',
    totalHt: data.totalHt || '1200',
    tva: data.tva || '20',
    totalTtc: data.totalTtc || '1440',
    notes: data.notes || 'Merci pour votre confiance.'
  };
  return compiled(mergedData);
}

app.get('/api/health', (req, res) => {
  res.json({ ok: true, dbReady });
});

app.get('/api/templates/default', (req, res) => {
  res.json({ html: defaultTemplate });
});

app.get('/api/recipients', async (req, res) => {
  if (dbReady && pool) {
    try {
      const result = await pool.query('SELECT * FROM recipients ORDER BY id ASC');
      return res.json(result.rows);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }
  return res.json(recipients);
});

app.post('/api/recipients', async (req, res) => {
  const { email, label } = req.body;

  if (!email || !label) {
    return res.status(400).json({ error: 'email and label are required' });
  }

  if (dbReady && pool) {
    try {
      const result = await pool.query(
        'INSERT INTO recipients (email, label) VALUES ($1, $2) RETURNING *',
        [email, label]
      );
      return res.json(result.rows[0]);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  const newRecipient = { id: recipients.length + 1, email, label };
  recipients.push(newRecipient);
  return res.json(newRecipient);
});

app.post('/api/preview', (req, res) => {
  const templateHtml = req.body.templateHtml || defaultTemplate;
  const html = renderTemplate(templateHtml, req.body);
  res.type('html').send(html);
});

app.post('/api/generate-pdf', async (req, res) => {
  try {
    const templateHtml = req.body.templateHtml || defaultTemplate;
    const html = renderTemplate(templateHtml, req.body);

    const browser = await puppeteer.launch({
      headless: 'new',
      args: ['--no-sandbox', '--disable-setuid-sandbox']
    });

    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'networkidle0' });
    const pdfBuffer = await page.pdf({
      format: 'A4',
      printBackground: true,
      margin: { top: '20px', right: '20px', bottom: '20px', left: '20px' }
    });
    await browser.close();

    res.json({
      filename: `${(req.body.invoiceNumber || 'document').replace(/\s+/g, '-')}.pdf`,
      base64: pdfBuffer.toString('base64')
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/documents', async (req, res) => {
  if (dbReady && pool) {
    try {
      const result = await pool.query(
        'SELECT id, name, mime_type, created_at FROM documents ORDER BY created_at DESC'
      );
      return res.json(result.rows);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  return res.json(
    memoryDocuments.map((doc) => ({
      id: doc.id,
      name: doc.name,
      mime_type: doc.mimeType,
      created_at: doc.createdAt
    }))
  );
});

app.post('/api/documents', async (req, res) => {
  const { name, pdfBase64 } = req.body;

  if (!name || !pdfBase64) {
    return res.status(400).json({ error: 'name and pdfBase64 are required' });
  }

  const buffer = Buffer.from(pdfBase64, 'base64');

  if (dbReady && pool) {
    try {
      const result = await pool.query(
        'INSERT INTO documents (name, document_blob, mime_type) VALUES ($1, $2, $3) RETURNING id, name',
        [name, buffer, 'application/pdf']
      );
      return res.json({ ok: true, id: result.rows[0].id, name: result.rows[0].name, storedInDb: true });
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  const id = memoryDocuments.length + 1;
  memoryDocuments.push({
    id,
    name,
    pdf: buffer,
    mimeType: 'application/pdf',
    createdAt: new Date().toISOString()
  });

  return res.json({ ok: true, id, name, storedInDb: false });
});

app.get('/api/documents/:id/download', async (req, res) => {
  const id = Number(req.params.id);

  if (dbReady && pool) {
    try {
      const result = await pool.query(
        'SELECT name, document_blob, mime_type FROM documents WHERE id = $1',
        [id]
      );

      if (!result.rows[0]) {
        return res.status(404).json({ error: 'Document not found' });
      }

      const doc = result.rows[0];
      res.setHeader('Content-Disposition', `attachment; filename="${doc.name}"`);
      res.setHeader('Content-Type', doc.mime_type);
      return res.send(doc.document_blob);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  const doc = memoryDocuments.find((item) => item.id === id);
  if (!doc) {
    return res.status(404).json({ error: 'Document not found' });
  }

  res.setHeader('Content-Disposition', `attachment; filename="${doc.name}"`);
  res.setHeader('Content-Type', doc.mimeType);
  return res.send(doc.pdf);
});

app.post('/api/upload-image', upload.single('image'), (req, res) => {
  if (!req.file) {
    return res.status(400).json({ error: 'image is required' });
  }

  const safeName = `${Date.now()}-${req.file.originalname.replace(/\s+/g, '-')}`;
  const filePath = path.join(uploadDir, safeName);
  fs.writeFileSync(filePath, req.file.buffer);

  res.json({
    url: `/uploads/${safeName}`,
    name: safeName
  });
});

app.post('/api/send-mail', async (req, res) => {
  const { to, subject, text } = req.body;

  if (!to || !subject || !text) {
    return res.status(400).json({ error: 'to, subject and text are required' });
  }

  const host = process.env.SMTP_HOST;
  const user = process.env.SMTP_USER;
  const pass = process.env.SMTP_PASS;

  if (!host || !user || !pass) {
    return res.status(400).json({
      error: 'SMTP is not configured. Add SMTP_HOST, SMTP_USER and SMTP_PASS in your .env file.'
    });
  }

  try {
    const transporter = nodemailer.createTransport({
      host,
      port: Number(process.env.SMTP_PORT || 587),
      secure: false,
      auth: { user, pass }
    });

    await transporter.sendMail({
      from: user,
      to,
      subject,
      text
    });

    return res.json({ ok: true });
  } catch (error) {
    return res.status(500).json({ error: error.message });
  }
});

app.get('*', (req, res) => {
  res.sendFile(path.join(__dirname, 'public', 'index.html'));
});

async function startServer() {
  await initDatabase();
  app.listen(PORT, () => {
    console.log(`Server running on http://localhost:${PORT}`);
  });
}

startServer();
