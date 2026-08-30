require('dotenv').config();

const express = require('express');
const path = require('path');
const fs = require('fs');
const multer = require('multer');
const nodemailer = require('nodemailer');
const handlebars = require('handlebars');
const mysql = require('mysql2/promise');
const { PDFDocument } = require('pdf-lib');
const { PublicClientApplication, ConfidentialClientApplication } = require('@azure/msal-node');

const app = express();
const PORT = process.env.PORT || 3000;
const uploadDir = path.join(__dirname, 'uploads');
const memoryDocuments = [];
const memoryDrivers = [
  { id: 1, name: 'Jean Martin', phone: '0600000001', license_number: 'AB12345' },
  { id: 2, name: 'Pierre Dubois', phone: '0600000002', license_number: 'CD67890' }
];
const memoryVehicles = [
  { id: 1, make: 'Mercedes', model: 'Sprinter', plate: 'AB-123-CD', capacity: '3.5 t' },
  { id: 2, make: 'Renault', model: 'Master', plate: 'EF-456-GH', capacity: '2.5 t' }
];
let recipients = [
  { id: 1, email: 'ikilinc07@gmail.com', label: 'Client principal' },
  { id: 2, email: 'support@example.com', label: 'Support' }
];
let templates = [];
let drivers = [...memoryDrivers];
let vehicles = [...memoryVehicles];

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
      body { font-family: Arial, sans-serif; margin: 30px; color: #1f2937; }
      .header { display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid #d1d5db; padding-bottom: 18px; margin-bottom: 20px; }
      .title { font-size: 28px; font-weight: bold; }
      .meta { font-size: 12px; color: #4b5563; }
      .grid { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin: 16px 0; }
      .card { border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }
      .label { font-weight: bold; }
      table { width: 100%; border-collapse: collapse; margin-top: 20px; }
      th, td { border: 1px solid #d1d5db; padding: 8px; text-align: left; }
      .totals { margin-top: 18px; text-align: right; }
      img { max-height: 60px; }
    </style>
  </head>
  <body>
    <div class="header">
      <div>
        <div class="title">Ordre de mission</div>
        <div class="meta">N° {{missionNumber}}</div>
      </div>
      <div class="meta">
        <img src="{{logoUrl}}" alt="Logo" /><br />
        {{companyName}}<br />
        {{companyAddress}}
      </div>
    </div>

    <div class="grid">
      <div class="card">
        <div><span class="label">Client :</span> {{clientName}}</div>
        <div><span class="label">Contact :</span> {{contactName}}</div>
        <div><span class="label">Téléphone :</span> {{contactPhone}}</div>
      </div>
      <div class="card">
        <div><span class="label">Chauffeur :</span> {{driverName}}</div>
        <div><span class="label">Véhicule :</span> {{vehicleLabel}}</div>
        <div><span class="label">Date :</span> {{missionDate}}</div>
      </div>
    </div>

    <table>
      <thead>
        <tr>
          <th>Départ</th>
          <th>Arrivée</th>
          <th>Distance</th>
          <th>Heure départ</th>
          <th>Heure arrivée</th>
          <th>Observation</th>
        </tr>
      </thead>
      <tbody>
        {{#each missionLines}}
        <tr>
          <td>{{this.from}}</td>
          <td>{{this.to}}</td>
          <td>{{this.distance}}</td>
          <td>{{this.departureTime}}</td>
          <td>{{this.arrivalTime}}</td>
          <td>{{this.note}}</td>
        </tr>
        {{/each}}
      </tbody>
    </table>

    <div class="totals">
      <div><span class="label">Distance totale :</span> {{totalDistance}} km</div>
      <div><span class="label">Observations :</span> {{notes}}</div>
    </div>
  </body>
</html>
`;

const upload = multer({ storage: multer.memoryStorage() });
let dbReady = false;
let pool = null;

function getDbConfig() {
  const defaultUrl = 'mysql://user:pass@dard.o2switch.net:3306/naqu7467_om';
  const databaseUrl = process.env.DATABASE_URL || defaultUrl;
  const url = new URL(databaseUrl);

  return {
    host: url.hostname,
    port: Number(url.port || 3306),
    user: decodeURIComponent(url.username),
    password: decodeURIComponent(url.password),
    database: decodeURIComponent(url.pathname.replace(/^\//, '')),
    ssl: { rejectUnauthorized: false },
    connectionLimit: 5
  };
}

function getDefaultMissionLines() {
  return [
    {
      from: 'Paris',
      to: 'Lyon',
      distance: '465',
      departureTime: '08:00',
      arrivalTime: '12:30',
      note: 'Trajet principal'
    },
    {
      from: 'Lyon',
      to: 'Grenoble',
      distance: '120',
      departureTime: '14:00',
      arrivalTime: '15:30',
      note: 'Livraison locale'
    }
  ];
}

function normalizeMissionData(data) {
  const missionLines = Array.isArray(data.missionLines) && data.missionLines.length > 0
    ? data.missionLines
    : getDefaultMissionLines();

  const totalDistance = missionLines.reduce((sum, item) => {
    const distanceValue = Number(String(item.distance).replace(',', '.').replace(/[^0-9.]/g, '') || 0);
    return sum + distanceValue;
  }, 0);

  return {
    ...data,
    logoUrl: data.logoUrl || '/uploads/logo-placeholder.png',
    missionNumber: data.missionNumber || 'OM-2026-001',
    companyName: data.companyName || 'BC Kent',
    companyAddress: data.companyAddress || '10 Avenue de la Mission, Lille',
    clientName: data.clientName || 'Client principal',
    contactName: data.contactName || 'Mr. Durand',
    contactPhone: data.contactPhone || '0600000000',
    driverName: data.driverName || drivers[0]?.name || 'Chauffeur principal',
    vehicleLabel: data.vehicleLabel || vehicles[0]?.plate || 'AB-123-CD',
    missionDate: data.missionDate || new Date().toISOString().slice(0, 10),
    notes: data.notes || 'Vérification des documents avant départ.',
    missionLines,
    totalDistance: totalDistance.toFixed(0)
  };
}

async function initDatabase() {
  try {
    pool = mysql.createPool(getDbConfig());
    await pool.query('SELECT 1 AS ok');
    dbReady = true;

    await pool.query(`
      CREATE TABLE IF NOT EXISTS recipients (
        id INT AUTO_INCREMENT PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        label VARCHAR(255) NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      ) ENGINE=InnoDB;
    `);

    await pool.query(`
      CREATE TABLE IF NOT EXISTS documents (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        document_data JSON,
        document_blob LONGBLOB,
        mime_type VARCHAR(100) DEFAULT 'application/pdf',
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      ) ENGINE=InnoDB;
    `);

    await pool.query(`
      CREATE TABLE IF NOT EXISTS templates (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        html_template LONGTEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      ) ENGINE=InnoDB;
    `);

    await pool.query(`
      CREATE TABLE IF NOT EXISTS drivers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        phone VARCHAR(50),
        license_number VARCHAR(100),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      ) ENGINE=InnoDB;
    `);

    await pool.query(`
      CREATE TABLE IF NOT EXISTS vehicles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        make VARCHAR(255),
        model VARCHAR(255),
        plate VARCHAR(50) NOT NULL UNIQUE,
        capacity VARCHAR(50),
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
      ) ENGINE=InnoDB;
    `);

    const [recipientCheck] = await pool.query('SELECT COUNT(*) AS count FROM recipients');
    if (Number(recipientCheck[0].count) === 0) {
      await pool.query(
        'INSERT INTO recipients (email, label) VALUES (?, ?), (?, ?)',
        ['client@example.com', 'Client principal', 'support@example.com', 'Support']
      );
    }

    const [templateCheck] = await pool.query('SELECT COUNT(*) AS count FROM templates');
    if (Number(templateCheck[0].count) === 0) {
      await pool.query(
        'INSERT INTO templates (name, html_template) VALUES (?, ?)',
        ['Ordre de mission standard', defaultTemplate]
      );
    }

    const [driversCheck] = await pool.query('SELECT COUNT(*) AS count FROM drivers');
    if (Number(driversCheck[0].count) === 0) {
      await pool.query(
        'INSERT INTO drivers (name, phone, license_number) VALUES (?, ?, ?), (?, ?, ?)',
        ['Jean Martin', '0600000001', 'AB12345', 'Pierre Dubois', '0600000002', 'CD67890']
      );
    }

    const [vehiclesCheck] = await pool.query('SELECT COUNT(*) AS count FROM vehicles');
    if (Number(vehiclesCheck[0].count) === 0) {
      await pool.query(
        'INSERT INTO vehicles (make, model, plate, capacity) VALUES (?, ?, ?, ?), (?, ?, ?, ?)',
        ['Mercedes', 'Sprinter', 'AB-123-CD', '3.5 t', 'Renault', 'Master', 'EF-456-GH', '2.5 t']
      );
    }

    const [recipientRows] = await pool.query('SELECT * FROM recipients ORDER BY id ASC');
    recipients = recipientRows;
    const [templateRows] = await pool.query('SELECT * FROM templates ORDER BY id ASC');
    templates = templateRows;
    const [driversRows] = await pool.query('SELECT * FROM drivers ORDER BY id ASC');
    drivers = driversRows;
    const [vehiclesRows] = await pool.query('SELECT * FROM vehicles ORDER BY id ASC');
    vehicles = vehiclesRows;

    console.log('MySQL ready.');
  } catch (error) {
    dbReady = false;
    console.warn('MySQL not available; continuing in fallback mode:', error.message);
  }
}

function renderTemplate(templateHtml, data) {
  const compiled = handlebars.compile(templateHtml || defaultTemplate);
  const mergedData = normalizeMissionData({
    ...data,
    logoUrl: data.logoUrl || '/uploads/logo-placeholder.png',
    driverName: data.driverName || drivers[0]?.name || 'Chauffeur principal',
    vehicleLabel: data.vehicleLabel || vehicles[0]?.plate || 'AB-123-CD'
  });
  return compiled(mergedData);
}

async function mergePdfDocuments(mainPdfBuffer, attachments = []) {
  if (!attachments.length) {
    return mainPdfBuffer;
  }

  const mergedPdf = await PDFDocument.create();
  const mainDocument = await PDFDocument.load(mainPdfBuffer);
  const mainPages = await mergedPdf.copyPages(mainDocument, mainDocument.getPageIndices());
  mainPages.forEach((page) => mergedPdf.addPage(page));

  for (const attachment of attachments) {
    if (!attachment || !attachment.base64) continue;

    const binaryPdf = Buffer.from(attachment.base64, 'base64');
    if (!binaryPdf.length) continue;

    const attachmentDoc = await PDFDocument.load(binaryPdf);
    const attachmentPages = await mergedPdf.copyPages(attachmentDoc, attachmentDoc.getPageIndices());
    attachmentPages.forEach((page) => mergedPdf.addPage(page));
  }

  return Buffer.from(await mergedPdf.save());
}

app.get('/api/health', (req, res) => {
  res.json({ ok: true, dbReady });
});

app.get('/api/templates', async (req, res) => {
  if (dbReady && pool) {
    try {
      const [result] = await pool.query('SELECT * FROM templates ORDER BY id ASC');
      templates = result;
      return res.json(result);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  return res.json(templates.length ? templates : [{ id: 1, name: 'Ordre de mission standard', html_template: defaultTemplate }]);
});

app.post('/api/templates', async (req, res) => {
  const { name, html_template } = req.body;

  if (!name || !html_template) {
    return res.status(400).json({ error: 'name and html_template are required' });
  }

  if (dbReady && pool) {
    try {
      const [insertResult] = await pool.query('INSERT INTO templates (name, html_template) VALUES (?, ?)', [name, html_template]);
      const [rows] = await pool.query('SELECT * FROM templates WHERE id = ?', [insertResult.insertId]);
      const saved = rows[0];
      templates = [...templates, saved];
      return res.json(saved);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  const newTemplate = { id: Date.now(), name, html_template };
  templates.push(newTemplate);
  return res.json(newTemplate);
});

app.get('/api/drivers', async (req, res) => {
  if (dbReady && pool) {
    try {
      const [result] = await pool.query('SELECT * FROM drivers ORDER BY id ASC');
      drivers = result;
      return res.json(result);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }
  return res.json(drivers);
});

app.post('/api/drivers', async (req, res) => {
  const { name, phone, license_number } = req.body;
  if (!name) {
    return res.status(400).json({ error: 'name is required' });
  }

  if (dbReady && pool) {
    try {
      const [insertResult] = await pool.query(
        'INSERT INTO drivers (name, phone, license_number) VALUES (?, ?, ?)',
        [name, phone || '', license_number || '']
      );
      const [rows] = await pool.query('SELECT * FROM drivers WHERE id = ?', [insertResult.insertId]);
      const saved = rows[0];
      drivers = [...drivers, saved];
      return res.json(saved);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  const newDriver = { id: Date.now(), name, phone: phone || '', license_number: license_number || '' };
  drivers.push(newDriver);
  return res.json(newDriver);
});

app.get('/api/vehicles', async (req, res) => {
  if (dbReady && pool) {
    try {
      const [result] = await pool.query('SELECT * FROM vehicles ORDER BY id ASC');
      vehicles = result;
      return res.json(result);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }
  return res.json(vehicles);
});

app.post('/api/vehicles', async (req, res) => {
  const { make, model, plate, capacity } = req.body;
  if (!plate) {
    return res.status(400).json({ error: 'plate is required' });
  }

  if (dbReady && pool) {
    try {
      const [insertResult] = await pool.query(
        'INSERT INTO vehicles (make, model, plate, capacity) VALUES (?, ?, ?, ?)',
        [make || '', model || '', plate, capacity || '']
      );
      const [rows] = await pool.query('SELECT * FROM vehicles WHERE id = ?', [insertResult.insertId]);
      const saved = rows[0];
      vehicles = [...vehicles, saved];
      return res.json(saved);
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  const newVehicle = { id: Date.now(), make: make || '', model: model || '', plate, capacity: capacity || '' };
  vehicles.push(newVehicle);
  return res.json(newVehicle);
});

app.get('/api/recipients', async (req, res) => {
  if (dbReady && pool) {
    try {
      const [result] = await pool.query('SELECT * FROM recipients ORDER BY id ASC');
      return res.json(result);
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
      const [insertResult] = await pool.query('INSERT INTO recipients (email, label) VALUES (?, ?)', [email, label]);
      const [rows] = await pool.query('SELECT * FROM recipients WHERE id = ?', [insertResult.insertId]);
      return res.json(rows[0]);
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
    const puppeteerModule = await import('puppeteer');
    const puppeteer = puppeteerModule.default || puppeteerModule;

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

    const attachments = Array.isArray(req.body.mergePdfs) ? req.body.mergePdfs : [];
    const finalPdfBuffer = await mergePdfDocuments(pdfBuffer, attachments);

    res.json({
      filename: `${(req.body.missionNumber || 'ordre-mission').replace(/\s+/g, '-')}.pdf`,
      base64: finalPdfBuffer.toString('base64')
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

app.get('/api/documents', async (req, res) => {
  if (dbReady && pool) {
    try {
      const [result] = await pool.query(
        'SELECT id, name, document_data, mime_type, created_at FROM documents ORDER BY created_at DESC'
      );
      return res.json(result.map((doc) => ({
        id: doc.id,
        name: doc.name,
        data: doc.document_data,
        mime_type: doc.mime_type,
        created_at: doc.created_at
      })));
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  return res.json(
    memoryDocuments.map((doc) => ({
      id: doc.id,
      name: doc.name,
      data: doc.data || {},
      mime_type: doc.mimeType,
      created_at: doc.createdAt
    }))
  );
});

app.get('/api/documents/:id', async (req, res) => {
  const id = Number(req.params.id);

  if (dbReady && pool) {
    try {
      const [result] = await pool.query(
        'SELECT id, name, document_data, document_blob, mime_type FROM documents WHERE id = ?',
        [id]
      );
      if (!result[0]) {
        return res.status(404).json({ error: 'Document non trouvé' });
      }
      return res.json({ ...result[0], data: result[0].document_data });
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  const doc = memoryDocuments.find((item) => item.id === id);
  if (!doc) {
    return res.status(404).json({ error: 'Document non trouvé' });
  }
  return res.json(doc);
});

app.post('/api/documents', async (req, res) => {
  const { name, pdfBase64, data } = req.body;

  if (!name) {
    return res.status(400).json({ error: 'name is required' });
  }

  const buffer = pdfBase64 ? Buffer.from(pdfBase64, 'base64') : Buffer.from('');

  if (dbReady && pool) {
    try {
      const [insertResult] = await pool.query(
        'INSERT INTO documents (name, document_data, document_blob, mime_type) VALUES (?, ?, ?, ?)',
        [name, JSON.stringify(data || {}), buffer, 'application/pdf']
      );
      return res.json({ ok: true, id: insertResult.insertId, name, storedInDb: true });
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  const id = memoryDocuments.length + 1;
  memoryDocuments.push({
    id,
    name,
    data: data || {},
    pdf: buffer,
    mimeType: 'application/pdf',
    createdAt: new Date().toISOString()
  });

  return res.json({ ok: true, id, name, storedInDb: false });
});

app.put('/api/documents/:id', async (req, res) => {
  const id = Number(req.params.id);
  const { name, pdfBase64, data } = req.body;

  if (!name) {
    return res.status(400).json({ error: 'name is required' });
  }

  if (dbReady && pool) {
    try {
      const [result] = await pool.query(
        'UPDATE documents SET name = ?, document_data = ?, document_blob = ? WHERE id = ?',
        [name, JSON.stringify(data || {}), pdfBase64 ? Buffer.from(pdfBase64, 'base64') : null, id]
      );
      if (result.affectedRows === 0) {
        return res.status(404).json({ error: 'Document non trouvé' });
      }
      return res.json({ ok: true, id, name, updated: true });
    } catch (error) {
      return res.status(500).json({ error: error.message });
    }
  }

  const doc = memoryDocuments.find((item) => item.id === id);
  if (!doc) {
    return res.status(404).json({ error: 'Document non trouvé' });
  }

  doc.name = name;
  doc.data = data || {};
  if (pdfBase64) {
    doc.pdf = Buffer.from(pdfBase64, 'base64');
  }
  return res.json({ ok: true, id: doc.id, name: doc.name, updated: true });
});

app.get('/api/documents/:id/download', async (req, res) => {
  const id = Number(req.params.id);

  if (dbReady && pool) {
    try {
      const [result] = await pool.query(
        'SELECT name, document_blob, mime_type FROM documents WHERE id = ?',
        [id]
      );

      if (!result[0]) {
        return res.status(404).json({ error: 'Document not found' });
      }

      const doc = result[0];
      res.setHeader('Content-Disposition', `attachment; filename="${doc.name}"`);
      res.setHeader('Content-Type', doc.mime_type);
      return res.send(doc.document_blob || Buffer.from(''));
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
  return res.send(doc.pdf || Buffer.from(''));
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

async function refreshSmtpAccessToken() {
  const authType = (process.env.SMTP_AUTH_TYPE || 'password').toLowerCase();
  if (authType !== 'oauth2') {
    return process.env.SMTP_ACCESS_TOKEN || null;
  }

  const refreshToken = process.env.SMTP_REFRESH_TOKEN;
  const clientId = process.env.SMTP_CLIENT_ID;
  const clientSecret = process.env.SMTP_CLIENT_SECRET;
  const tenantId = process.env.SMTP_TENANT_ID;
  const expiresAt = Number(process.env.SMTP_ACCESS_TOKEN_EXPIRES_AT || 0);
  const now = Date.now();

  if (process.env.SMTP_ACCESS_TOKEN && expiresAt > now + 300000) {
    return process.env.SMTP_ACCESS_TOKEN;
  }

  if (!refreshToken || !clientId || !tenantId) {
    return process.env.SMTP_ACCESS_TOKEN || null;
  }

  try {
    const msalConfig = {
      auth: {
        clientId,
        authority: `https://login.microsoftonline.com/${tenantId}`
      }
    };

    if (clientSecret) {
      msalConfig.auth.clientSecret = clientSecret;
    }

    const app = clientSecret
      ? new ConfidentialClientApplication(msalConfig)
      : new PublicClientApplication(msalConfig);

    const result = await app.acquireTokenByRefreshToken({
      refreshToken,
      scopes: ['https://outlook.office.com/SMTP.Send', 'offline_access', 'openid', 'profile']
    });

    if (!result || !result.accessToken) {
      return process.env.SMTP_ACCESS_TOKEN || null;
    }

    const nextExpiresAt = result.expiresOn ? result.expiresOn.getTime() : now + 3600000;
    process.env.SMTP_ACCESS_TOKEN = result.accessToken;
    process.env.SMTP_ACCESS_TOKEN_EXPIRES_AT = String(nextExpiresAt);

    const envPath = path.join(__dirname, '.env');
    if (fs.existsSync(envPath)) {
      let envContent = fs.readFileSync(envPath, 'utf8');
      envContent = envContent.replace(/^SMTP_ACCESS_TOKEN=.*$/m, `SMTP_ACCESS_TOKEN=${result.accessToken}`);
      envContent = envContent.replace(/^SMTP_ACCESS_TOKEN_EXPIRES_AT=.*$/m, `SMTP_ACCESS_TOKEN_EXPIRES_AT=${nextExpiresAt}`);
      if (!/^SMTP_ACCESS_TOKEN=.*$/m.test(envContent)) {
        envContent += `\nSMTP_ACCESS_TOKEN=${result.accessToken}\nSMTP_ACCESS_TOKEN_EXPIRES_AT=${nextExpiresAt}\n`;
      }
      fs.writeFileSync(envPath, envContent);
    }

    return result.accessToken;
  } catch (error) {
    console.warn('SMTP token refresh failed:', error.message || error);
    return process.env.SMTP_ACCESS_TOKEN || null;
  }
}

async function buildSmtpTransport() {
  const host = process.env.SMTP_HOST || 'smtp.office365.com';
  const port = Number(process.env.SMTP_PORT || 587);
  const secure = String(process.env.SMTP_SECURE || 'false').toLowerCase() === 'true';
  const authType = (process.env.SMTP_AUTH_TYPE || 'password').toLowerCase();
  const user = process.env.SMTP_USER;

  if (authType === 'oauth2') {
    const accessToken = await refreshSmtpAccessToken();
    if (!host || !user || !accessToken) {
      throw new Error(
        'OAuth2 SMTP is not configured. Set SMTP_HOST, SMTP_USER, SMTP_ACCESS_TOKEN and SMTP_AUTH_TYPE=oauth2 in your .env file. Optional values: SMTP_CLIENT_ID, SMTP_CLIENT_SECRET, SMTP_TENANT_ID, SMTP_REFRESH_TOKEN.'
      );
    }

    const oauthConfig = {
      type: 'OAuth2',
      user,
      accessToken,
      refreshToken: process.env.SMTP_REFRESH_TOKEN,
      expires: process.env.SMTP_ACCESS_TOKEN_EXPIRES_AT ? Number(process.env.SMTP_ACCESS_TOKEN_EXPIRES_AT) : 0
    };

    if (process.env.SMTP_CLIENT_ID) {
      oauthConfig.clientId = process.env.SMTP_CLIENT_ID;
    }
    if (process.env.SMTP_CLIENT_SECRET) {
      oauthConfig.clientSecret = process.env.SMTP_CLIENT_SECRET;
    }
    if (process.env.SMTP_TENANT_ID) {
      oauthConfig.tenantId = process.env.SMTP_TENANT_ID;
    }

    return nodemailer.createTransport({
      host,
      port,
      secure,
      auth: oauthConfig
    });
  }

  const pass = process.env.SMTP_PASS;
  if (!host || !user || !pass) {
    throw new Error(
      'SMTP is not configured. Add SMTP_HOST, SMTP_USER and SMTP_PASS in your .env file. For Microsoft 365, you can also use SMTP_AUTH_TYPE=oauth2 with Azure app registration.'
    );
  }

  return nodemailer.createTransport({
    host,
    port,
    secure,
    auth: { user, pass }
  });
}

app.post('/api/send-mail', async (req, res) => {
  const { to, subject, text } = req.body;

  if (!to || !subject || !text) {
    return res.status(400).json({ error: 'to, subject and text are required' });
  }

  try {
    const transporter = await buildSmtpTransport();
    const from = process.env.SMTP_FROM || process.env.SMTP_USER;

    await transporter.sendMail({
      from,
      to,
      subject,
      text
    });

    return res.json({ ok: true, provider: 'smtp' });
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

if (require.main === module) {
  startServer();
}

module.exports = app;
