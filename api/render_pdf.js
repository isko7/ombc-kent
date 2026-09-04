// Fonction serverless Node : rend une chaîne HTML en PDF via Chrome headless.
// Appelée en interne par l'app Flask (app/pdf_service.py, PDF_ENGINE=http).
//
// POST /api/render_pdf   { "html": "<!doctype html>..." }  -> application/pdf
//
// Le rendu respecte les règles CSS @page (size / margin) des templates
// grâce à preferCSSPageSize, pour rester proche de la sortie wkhtmltopdf.

const path = require('path');
const chromium = require('@sparticuz/chromium');
const puppeteer = require('puppeteer-core');

// Pas de WebGL/GPU : inutile pour un rendu PDF, et plus rapide au démarrage.
chromium.setGraphicsMode = false;

// Polices : le runtime Vercel n'a quasiment aucune police -> les glyphes
// non-ASCII (flèche →, etc.) et le rendu global seraient dégradés. On
// enregistre DejaVu Sans (que les templates demandent explicitement) avant
// le lancement de Chrome. includeFiles: "fonts/**" dans vercel.json garantit
// que les .ttf sont dans le bundle de la fonction.
const FONT_DIR = path.join(process.cwd(), 'fonts');
let fontsReady;
function registerFonts() {
  if (!fontsReady) {
    fontsReady = Promise.all([
      chromium.font(path.join(FONT_DIR, 'DejaVuSans.ttf')),
      chromium.font(path.join(FONT_DIR, 'DejaVuSans-Bold.ttf')),
    ]).catch((e) => { console.error('font register failed:', e && e.message); });
  }
  return fontsReady;
}

async function readJsonBody(req) {
  if (req.body) {
    return typeof req.body === 'string' ? JSON.parse(req.body) : req.body;
  }
  const chunks = [];
  for await (const chunk of req) chunks.push(chunk);
  const raw = Buffer.concat(chunks).toString('utf-8');
  return raw ? JSON.parse(raw) : {};
}

module.exports = async (req, res) => {
  if (req.method !== 'POST') {
    res.status(405).json({ error: 'Method Not Allowed' });
    return;
  }

  const secret = process.env.PDF_RENDER_SECRET;
  if (secret && req.headers['x-render-secret'] !== secret) {
    res.status(401).json({ error: 'Unauthorized' });
    return;
  }

  let html;
  try {
    ({ html } = await readJsonBody(req));
  } catch (e) {
    res.status(400).json({ error: 'Corps JSON invalide' });
    return;
  }
  if (!html || typeof html !== 'string') {
    res.status(400).json({ error: 'Champ "html" manquant' });
    return;
  }

  let browser;
  try {
    await registerFonts();
    browser = await puppeteer.launch({
      args: chromium.args,
      defaultViewport: chromium.defaultViewport,
      executablePath: await chromium.executablePath(),
      headless: true,
    });
    const page = await browser.newPage();
    await page.setContent(html, { waitUntil: 'networkidle0', timeout: 30000 });
    const pdf = await page.pdf({
      preferCSSPageSize: true,
      printBackground: true,
      format: 'A4',
    });
    res.setHeader('Content-Type', 'application/pdf');
    res.setHeader('Content-Length', pdf.length);
    res.status(200).send(Buffer.from(pdf));
  } catch (e) {
    res.status(500).json({ error: 'Échec du rendu PDF : ' + (e && e.message) });
  } finally {
    if (browser) await browser.close();
  }
};
