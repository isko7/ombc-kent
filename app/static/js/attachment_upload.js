// Pièce jointe : glisser-déposer + choix des pages d'un PDF à joindre.
//
// Le rendu des miniatures se fait entièrement dans le navigateur via
// PDF.js (chargé en <script type="module"> dans missions/detail.html) :
// aucun envoi au serveur tant que l'utilisateur n'a pas choisi les pages
// et cliqué "Joindre". Si PDF.js ne se charge pas (CDN bloqué), le picker
// ne s'affiche simplement pas et le PDF entier est joint tel quel.

function waitForPdfJs(timeoutMs) {
  return new Promise((resolve) => {
    if (window.pdfjsLib) { resolve(window.pdfjsLib); return; }
    const start = Date.now();
    const t = setInterval(() => {
      if (window.pdfjsLib || Date.now() - start > timeoutMs) {
        clearInterval(t);
        resolve(window.pdfjsLib || null);
      }
    }, 100);
  });
}

function initAttachmentUpload() {
  const dropzone = document.getElementById("attach-dropzone");
  const fileInput = document.getElementById("attach-file");
  if (!dropzone || !fileInput) return;

  const filenameEl = document.getElementById("attach-filename");
  const pagesInput = document.getElementById("attach-pages");
  const pickerBox = document.getElementById("attach-page-picker");
  const thumbsEl = document.getElementById("attach-thumbs");
  const pageCountEl = document.getElementById("attach-page-count");
  const form = document.getElementById("attach-form");

  let selectedPages = new Set();

  dropzone.addEventListener("click", () => fileInput.click());
  dropzone.addEventListener("dragover", (e) => {
    e.preventDefault();
    dropzone.classList.add("dropzone--over");
  });
  dropzone.addEventListener("dragleave", () => dropzone.classList.remove("dropzone--over"));
  dropzone.addEventListener("drop", (e) => {
    e.preventDefault();
    dropzone.classList.remove("dropzone--over");
    if (e.dataTransfer.files && e.dataTransfer.files.length) {
      fileInput.files = e.dataTransfer.files;
      handleFile(fileInput.files[0]);
    }
  });
  fileInput.addEventListener("change", () => {
    if (fileInput.files.length) handleFile(fileInput.files[0]);
  });

  function resetPicker() {
    selectedPages = new Set();
    pagesInput.value = "";
    pickerBox.hidden = true;
    thumbsEl.innerHTML = "";
  }

  function handleFile(file) {
    filenameEl.textContent = file.name;
    resetPicker();
    const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
    if (isPdf) renderPdfPicker(file);
  }

  async function renderPdfPicker(file) {
    const pdfjsLib = await waitForPdfJs(3000);
    if (!pdfjsLib) return; // pas de picker -> le PDF entier sera joint

    let pdf;
    try {
      const buf = await file.arrayBuffer();
      pdf = await pdfjsLib.getDocument({ data: buf }).promise;
    } catch (e) {
      return; // PDF illisible côté navigateur : on laisse le serveur décider
    }

    pageCountEl.textContent = pdf.numPages;
    pickerBox.hidden = false;

    for (let i = 1; i <= pdf.numPages; i++) {
      const page = await pdf.getPage(i);
      const viewport = page.getViewport({ scale: 0.28 });
      const canvas = document.createElement("canvas");
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvasContext: canvas.getContext("2d"), viewport }).promise;

      const thumb = document.createElement("div");
      thumb.className = "attach-thumb";
      const label = document.createElement("div");
      label.className = "attach-thumb__label";
      label.textContent = "Page " + i;
      thumb.appendChild(canvas);
      thumb.appendChild(label);
      thumb.addEventListener("click", () => togglePage(i, thumb));
      thumbsEl.appendChild(thumb);
    }
    // Première page sélectionnée par défaut (cas le plus courant : joindre
    // une seule page d'un PDF plus long).
    if (thumbsEl.firstElementChild) thumbsEl.firstElementChild.click();
  }

  function togglePage(n, thumb) {
    if (selectedPages.has(n)) {
      selectedPages.delete(n);
      thumb.classList.remove("selected");
    } else {
      selectedPages.add(n);
      thumb.classList.add("selected");
    }
    pagesInput.value = Array.from(selectedPages).sort((a, b) => a - b).join(",");
  }

  if (form) {
    form.addEventListener("submit", (e) => {
      if (!pickerBox.hidden && selectedPages.size === 0) {
        e.preventDefault();
        alert("Choisissez au moins une page du PDF à joindre.");
      }
    });
  }
}

document.addEventListener("DOMContentLoaded", initAttachmentUpload);
