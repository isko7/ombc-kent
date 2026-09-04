// Fonction serverless Node : rend une chaîne HTML en PDF via Chrome headless.
// Appelée en interne par l'app Flask (app/pdf_service.py, PDF_ENGINE=http).
//
// POST /api/render_pdf   { "html": "<!doctype html>..." }  -> application/pdf
//
// Le rendu respecte les règles CSS @page (size / margin) des templates
// grâce à preferCSSPageSize, pour rester proche de la sortie wkhtmltopdf.

const fs = require('fs');
const path = require('path');
const chromium = require('@sparticuz/chromium');
const puppeteer = require('puppeteer-core');

// Pas de WebGL/GPU : inutile pour un rendu PDF, et plus rapide au démarrage.
chromium.setGraphicsMode = false;

// Le runtime Vercel n'a quasiment aucune police -> certains glyphes
// (flèche →, etc.) manquent. On injecte DejaVu Sans en @font-face base64
// dans le HTML : c'est une web-font au niveau page, ça ne touche pas la
// config fontconfig de Chrome (donc pas de risque de casser le reste).
// includeFiles: "fonts/**" dans vercel.json embarque les .ttf.
let FONT_CSS = null;
function fontFaceCss() {
  if (FONT_CSS !== null) return FONT_CSS;
  try {
    const dir = path.join(process.cwd(), 'fonts');
    const reg = fs.readFileSync(path.join(dir, 'DejaVuSans.ttf')).toString('base64');
    const bold = fs.readFileSync(path.join(dir, 'DejaVuSans-Bold.ttf')).toString('base64');
    FONT_CSS =
      '<style>' +
      "@font-face{font-family:'DejaVu Sans';font-weight:400;font-style:normal;" +
      'src:url(data:font/ttf;base64,' + reg + ') format("truetype")}' +
      "@font-face{font-family:'DejaVu Sans';font-weight:700;font-style:normal;" +
      'src:url(data:font/ttf;base64,' + bold + ') format("truetype")}' +
      '</style>';
  } catch (e) {
    console.error('fontFaceCss: fonts introuvables, rendu sans DejaVu:', e && e.message);
    FONT_CSS = '';
  }
  return FONT_CSS;
}

function injectFonts(html) {
  const css = fontFaceCss();
  if (!css) return html;
  if (/<head[^>]*>/i.test(html)) return html.replace(/<head[^>]*>/i, (m) => m + css);
  if (/<html[^>]*>/i.test(html)) return html.replace(/<html[^>]*>/i, (m) => m + css);
  return css + html;
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
    browser = await puppeteer.launch({
      args: chromium.args,
      defaultViewport: chromium.defaultViewport,
      executablePath: await chromium.executablePath(),
      headless: true,
    });
    const page = await browser.newPage();
    await page.setContent(injectFonts(html), { waitUntil: 'networkidle0', timeout: 30000 });
    await page.evaluateHandle('document.fonts.ready');
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
