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

const templateEditor = document.getElementById('templateHtml');
templateEditor.value = defaultTemplate;

const formFields = [
  'documentName', 'invoiceNumber', 'companyName', 'companyAddress', 'customerName',
  'customerEmail', 'date', 'service1', 'qty1', 'unitPrice1', 'total1', 'totalHt',
  'tva', 'totalTtc', 'notes'
];

let logoUrl = '/uploads/logo-placeholder.png';
let generatedPdfBase64 = '';
let generatedDocumentName = '';

function readFormValues() {
  const payload = {};
  for (const field of formFields) {
    const input = document.getElementById(field);
    payload[field] = input ? input.value : '';
  }
  payload.logoUrl = logoUrl;
  payload.templateHtml = templateEditor.value;
  return payload;
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

  const name = document.getElementById('documentName').value || generatedDocumentName || 'document.pdf';
  const response = await fetch('/api/documents', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, pdfBase64: generatedPdfBase64 })
  });

  const data = await response.json();
  if (!response.ok) {
    alert(data.error || 'Erreur lors de l’enregistrement');
    return;
  }

  alert(`Document enregistré : ${data.name}`);
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
  a.download = generatedDocumentName || 'document.pdf';
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

formFields.forEach((field) => {
  const input = document.getElementById(field);
  if (input) {
    input.addEventListener('input', renderPreview);
  }
});

templateEditor.addEventListener('input', renderPreview);
document.getElementById('previewBtn').addEventListener('click', renderPreview);
document.getElementById('generateBtn').addEventListener('click', generatePdf);
document.getElementById('saveBtn').addEventListener('click', saveDocument);
document.getElementById('downloadBtn').addEventListener('click', downloadDocument);
document.getElementById('sendMailBtn').addEventListener('click', sendMail);
document.getElementById('uploadImageBtn').addEventListener('click', uploadImage);

loadRecipients();
renderPreview();
