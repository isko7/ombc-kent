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

const templateEditor = document.getElementById('templateHtml');
templateEditor.value = defaultTemplate;

const formFields = [
  'documentName', 'missionNumber', 'clientName', 'contactName', 'contactPhone', 'companyName',
  'companyAddress', 'missionDate', 'notes'
];

let logoUrl = '/uploads/logo-placeholder.png';
let generatedPdfBase64 = '';
let generatedDocumentName = '';
let currentDocumentId = null;
let attachedPdfFiles = [];

function renderAttachedPdfList() {
  const container = document.getElementById('mergePdfList');
  if (!container) return;

  if (!attachedPdfFiles.length) {
    container.innerHTML = '<div class="empty-list">Aucun PDF ajouté.</div>';
    return;
  }

  container.innerHTML = attachedPdfFiles.map((item, index) => `
    <div class="attached-pdf-item">
      <span>${item.name}</span>
      <button type="button" class="remove-pdf-btn" data-index="${index}">Retirer</button>
    </div>
  `).join('');

  container.querySelectorAll('.remove-pdf-btn').forEach((button) => {
    button.addEventListener('click', () => {
      const index = Number(button.dataset.index);
      attachedPdfFiles.splice(index, 1);
      renderAttachedPdfList();
      renderPreview();
    });
  });
}

function readPdfFileAsBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => {
      const result = reader.result;
      const base64 = typeof result === 'string'
        ? result.split(',')[1]
        : Buffer.from(result).toString('base64');
      resolve(base64);
    };
    reader.onerror = () => reject(new Error('Impossible de lire le PDF'));
    reader.readAsDataURL(file);
  });
}

async function uploadPdfAttachments() {
  const input = document.getElementById('mergePdfUpload');
  const files = Array.from(input.files || []);

  if (!files.length) {
    alert('Choisissez au moins un fichier PDF');
    return;
  }

  for (const file of files) {
    if (file.type !== 'application/pdf' && !file.name.toLowerCase().endsWith('.pdf')) {
      alert(`Le fichier "${file.name}" n’est pas un PDF valide.`);
      continue;
    }

    const base64 = await readPdfFileAsBase64(file);
    attachedPdfFiles.push({ name: file.name, base64 });
  }

  input.value = '';
  renderAttachedPdfList();
  renderPreview();
}

function getDefaultMissionLines() {
  return [
    { from: 'Paris', to: 'Lyon', distance: '465', departureTime: '08:00', arrivalTime: '12:30', note: 'Trajet principal' },
    { from: 'Lyon', to: 'Grenoble', distance: '120', departureTime: '14:00', arrivalTime: '15:30', note: 'Livraison locale' }
  ];
}

function readMissionLines() {
  const lines = [];
  const rows = document.querySelectorAll('#missionLines .mission-row');
  rows.forEach((row) => {
    const values = {
      from: row.querySelector('[data-field="from"]').value,
      to: row.querySelector('[data-field="to"]').value,
      distance: row.querySelector('[data-field="distance"]').value,
      departureTime: row.querySelector('[data-field="departureTime"]').value,
      arrivalTime: row.querySelector('[data-field="arrivalTime"]').value,
      note: row.querySelector('[data-field="note"]').value
    };
    if (values.from || values.to || values.distance || values.departureTime || values.arrivalTime || values.note) {
      lines.push(values);
    }
  });
  return lines.length ? lines : getDefaultMissionLines();
}

function renderMissionRows(lines = getDefaultMissionLines()) {
  const container = document.getElementById('missionLines');
  container.innerHTML = '';

  lines.forEach((line, index) => {
    const row = document.createElement('div');
    row.className = 'mission-row';
    row.innerHTML = `
      <div class="mission-row-grid">
        <input data-field="from" value="${line.from || ''}" placeholder="Départ" />
        <input data-field="to" value="${line.to || ''}" placeholder="Arrivée" />
        <input data-field="distance" value="${line.distance || ''}" placeholder="Km" />
        <input data-field="departureTime" value="${line.departureTime || ''}" placeholder="Heure départ" />
        <input data-field="arrivalTime" value="${line.arrivalTime || ''}" placeholder="Heure arrivée" />
        <input data-field="note" value="${line.note || ''}" placeholder="Observation" />
        <button type="button" class="danger-btn" data-index="${index}">Supprimer</button>
      </div>
    `;
    container.appendChild(row);
  });

  container.querySelectorAll('.danger-btn').forEach((button) => {
    button.addEventListener('click', () => {
      const rows = [...document.querySelectorAll('#missionLines .mission-row')];
      rows[Number(button.dataset.index)].remove();
      renderMissionRows(readMissionLines());
      renderPreview();
    });
  });
}

function addMissionRow() {
  const currentRows = readMissionLines();
  currentRows.push({ from: '', to: '', distance: '', departureTime: '', arrivalTime: '', note: '' });
  renderMissionRows(currentRows);
}

async function loadDrivers() {
  try {
    const response = await fetch('/api/drivers');
    const drivers = await response.json();
    const select = document.getElementById('driverSelect');
    select.innerHTML = '';
    drivers.forEach((driver) => {
      const option = document.createElement('option');
      option.value = driver.name;
      option.textContent = `${driver.name} (${driver.license_number || 'Permis'})`;
      select.appendChild(option);
    });
  } catch (error) {
    console.error('Drivers load failed', error);
  }
}

async function loadVehicles() {
  try {
    const response = await fetch('/api/vehicles');
    const vehicles = await response.json();
    const select = document.getElementById('vehicleSelect');
    select.innerHTML = '';
    vehicles.forEach((vehicle) => {
      const option = document.createElement('option');
      option.value = `${vehicle.make || ''} ${vehicle.model || ''} - ${vehicle.plate}`;
      option.textContent = `${vehicle.make || ''} ${vehicle.model || ''} - ${vehicle.plate}`;
      select.appendChild(option);
    });
  } catch (error) {
    console.error('Vehicles load failed', error);
  }
}

async function loadTemplates() {
  try {
    const response = await fetch('/api/templates');
    const templates = await response.json();
    const select = document.getElementById('templateSelect');
    select.innerHTML = '';
    templates.forEach((template) => {
      const option = document.createElement('option');
      option.value = String(template.id);
      option.textContent = template.name;
      select.appendChild(option);
    });
    if (templates.length) {
      templateEditor.value = templates[0].html_template || defaultTemplate;
    }
  } catch (error) {
    console.error('Templates load failed', error);
  }
}

async function saveTemplate() {
  const name = window.prompt('Nom du template ?', 'Ordre de mission standard');
  if (!name) return;

  const response = await fetch('/api/templates', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, html_template: templateEditor.value })
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || 'Erreur lors de l’enregistrement du template');
    return;
  }
  alert(`Template enregistré : ${data.name}`);
  loadTemplates();
}

async function loadSelectedTemplate() {
  const templateId = document.getElementById('templateSelect').value;
  const response = await fetch('/api/templates');
  const templates = await response.json();
  const selected = templates.find((template) => String(template.id) === String(templateId));
  if (!selected) return;
  templateEditor.value = selected.html_template || defaultTemplate;
  renderPreview();
}

async function loadDocuments() {
  try {
    const response = await fetch('/api/documents');
    const documents = await response.json();
    const select = document.getElementById('documentSelect');
    select.innerHTML = '';
    documents.forEach((doc) => {
      const option = document.createElement('option');
      option.value = String(doc.id);
      option.textContent = doc.name;
      select.appendChild(option);
    });
  } catch (error) {
    console.error('Documents load failed', error);
  }
}

async function loadDocumentById(documentId) {
  const response = await fetch(`/api/documents/${documentId}`);
  const doc = await response.json();
  if (!response.ok) {
    alert(doc.error || 'Document introuvable');
    return;
  }

  const payload = doc.data || {};
  currentDocumentId = doc.id;
  attachedPdfFiles = Array.isArray(payload.mergePdfs) ? payload.mergePdfs : [];
  renderAttachedPdfList();

  for (const field of formFields) {
    const input = document.getElementById(field);
    if (input) input.value = payload[field] || '';
  }

  const driverName = payload.driverName || '';
  const vehicleValue = payload.vehicleLabel || '';
  document.getElementById('driverSelect').value = driverName;
  document.getElementById('vehicleSelect').value = vehicleValue;
  templateEditor.value = payload.templateHtml || defaultTemplate;
  renderMissionRows(payload.missionLines || getDefaultMissionLines());
  renderPreview();
}

async function loadRecipients() {
  try {
    const response = await fetch('/api/recipients');
    const recipients = await response.json();
    const select = document.getElementById('recipientSelect');
    select.innerHTML = '';
    recipients.forEach((recipient) => {
      const option = document.createElement('option');
      option.value = recipient.email;
      option.textContent = `${recipient.label} (${recipient.email})`;
      select.appendChild(option);
    });
  } catch (error) {
    console.error('Recipients load failed', error);
  }
}

function readFormValues() {
  const payload = {};
  for (const field of formFields) {
    const input = document.getElementById(field);
    payload[field] = input ? input.value : '';
  }
  payload.driverName = document.getElementById('driverSelect').value;
  payload.vehicleLabel = document.getElementById('vehicleSelect').value;
  payload.logoUrl = logoUrl;
  payload.templateHtml = templateEditor.value;
  payload.missionLines = readMissionLines();
  payload.mergePdfs = attachedPdfFiles;
  payload.totalDistance = payload.missionLines.reduce((sum, item) => {
    const value = Number(String(item.distance).replace(',', '.').replace(/[^0-9.]/g, '') || 0);
    return sum + value;
  }, 0).toFixed(0);
  return payload;
}

async function renderPreview() {
  const payload = readFormValues();
  const response = await fetch('/api/preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const html = await response.text();
  document.getElementById('previewFrame').srcdoc = html;
}

async function generatePdf() {
  const payload = readFormValues();
  const response = await fetch('/api/generate-pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload)
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || 'Erreur lors de la génération du PDF');
    return;
  }
  generatedPdfBase64 = data.base64;
  generatedDocumentName = data.filename;
  alert('PDF généré avec succès');
}

async function saveDocument() {
  if (!generatedPdfBase64) {
    await generatePdf();
  }

  const payload = readFormValues();
  const name = document.getElementById('documentName').value || generatedDocumentName || 'ordre-mission.pdf';

  const body = { name, pdfBase64: generatedPdfBase64, data: payload };

  const endpoint = currentDocumentId ? `/api/documents/${currentDocumentId}` : '/api/documents';
  const method = currentDocumentId ? 'PUT' : 'POST';

  const response = await fetch(endpoint, {
    method,
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body)
  });

  const data = await response.json();
  if (!response.ok) {
    alert(data.error || 'Erreur lors de l’enregistrement');
    return;
  }

  currentDocumentId = data.id || currentDocumentId;
  alert(`Document enregistré : ${data.name || name}`);
  loadDocuments();
}

async function downloadDocument() {
  if (!generatedPdfBase64) {
    await generatePdf();
  }

  const byteCharacters = atob(generatedPdfBase64);
  const byteNumbers = new Array(byteCharacters.length);
  for (let i = 0; i < byteCharacters.length; i++) {
    byteNumbers[i] = byteCharacters.charCodeAt(i);
  }
  const byteArray = new Uint8Array(byteNumbers);
  const blob = new Blob([byteArray], { type: 'application/pdf' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = generatedDocumentName || 'ordre-mission.pdf';
  a.click();
  URL.revokeObjectURL(url);
}

async function sendMail() {
  const to = document.getElementById('recipientSelect').value;
  const subject = document.getElementById('mailSubject').value;
  const text = document.getElementById('mailBody').value;

  const response = await fetch('/api/send-mail', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ to, subject, text })
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || 'Erreur lors de l’envoi du mail');
    return;
  }
  alert('Email envoyé');
}

async function uploadImage() {
  const fileInput = document.getElementById('imageUpload');
  const file = fileInput.files[0];
  if (!file) {
    alert('Choisissez une image');
    return;
  }

  const formData = new FormData();
  formData.append('image', file);

  const response = await fetch('/api/upload-image', {
    method: 'POST',
    body: formData
  });
  const data = await response.json();
  if (!response.ok) {
    alert(data.error || 'Erreur lors du chargement de l’image');
    return;
  }

  logoUrl = data.url;
  document.getElementById('uploadedPreview').src = logoUrl;
  document.getElementById('uploadedPreview').style.display = 'block';
  renderPreview();
}

for (const field of formFields) {
  const input = document.getElementById(field);
  if (input) {
    input.addEventListener('input', renderPreview);
  }
}

document.getElementById('driverSelect').addEventListener('change', renderPreview);
document.getElementById('vehicleSelect').addEventListener('change', renderPreview);
document.getElementById('templateHtml').addEventListener('input', renderPreview);
document.getElementById('previewBtn').addEventListener('click', renderPreview);
document.getElementById('generateBtn').addEventListener('click', generatePdf);
document.getElementById('saveBtn').addEventListener('click', saveDocument);
document.getElementById('downloadBtn').addEventListener('click', downloadDocument);
document.getElementById('saveTemplateBtn').addEventListener('click', saveTemplate);
document.getElementById('loadTemplateBtn').addEventListener('click', loadSelectedTemplate);
document.getElementById('sendMailBtn').addEventListener('click', sendMail);
document.getElementById('uploadImageBtn').addEventListener('click', uploadImage);
document.getElementById('uploadPdfBtn').addEventListener('click', uploadPdfAttachments);
document.getElementById('addLineBtn').addEventListener('click', () => {
  const lines = readMissionLines();
  lines.push({ from: '', to: '', distance: '', departureTime: '', arrivalTime: '', note: '' });
  renderMissionRows(lines);
  renderPreview();
});
document.getElementById('loadDocumentBtn').addEventListener('click', () => {
  const selectedId = document.getElementById('documentSelect').value;
  if (selectedId) loadDocumentById(selectedId);
});

renderMissionRows(getDefaultMissionLines());
renderAttachedPdfList();
loadRecipients();
loadDrivers();
loadVehicles();
loadTemplates();
loadDocuments();
renderPreview();
