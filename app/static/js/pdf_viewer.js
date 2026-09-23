// Visionneuse flottante (floating_panel.js) : le fichier choisi dans
// Pièces jointes (« Agrandir ») et l'ordre de mission généré (« Aperçu
// PDF »), à comparer avec la page. Les PDF sont dessinés par PDF.js plutôt
// que confiés au lecteur du navigateur, qui peut être réglé pour les
// télécharger au lieu de les afficher.

// PDF.js est chargé en module (missions/_pdf_tools.html), donc après la
// page. null si le CDN ne répond pas. Sert aussi aux miniatures
// (attachment_upload.js) et à la lecture des arrêts (stops_ocr.js).
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

window.KentPdfViewer = window.KentPdfViewer || (function () {
  let viewer = null;
  let doc = null;        // document PDF.js affiché
  let objectUrl = null;  // fichier local, pour « ouvrir dans un nouvel onglet »
  let shown = 0;         // dernier affichage demandé
  let drawn = 0;         // dernier dessin demandé
  let resizeTimer = null;

  function panel() {
    viewer = viewer || KentFloat.create({
      name: "document", label: "Document", className: "float-panel--viewer",
      storageKey: "kent.documentFloat", widthRatio: 0.5, maxWidth: 900,
      onClose: reset,
      // Pages redessinées à la nouvelle largeur, pour rester nettes.
      onResize: () => {
        clearTimeout(resizeTimer);
        resizeTimer = setTimeout(draw, 250);
      },
    });
    return viewer;
  }

  function reset() {
    shown++;
    if (doc) doc.destroy();
    doc = null;
    if (objectUrl) URL.revokeObjectURL(objectUrl);
    objectUrl = null;
  }

  function message(text, isError) {
    const p = document.createElement("p");
    p.className = "hint" + (isError ? " is-error" : "");
    p.textContent = text;
    viewer.body.replaceChildren(p);
  }

  // Toutes les pages, à la largeur du panneau (résolution de l'écran).
  async function draw() {
    if (!doc) return;
    const mine = ++drawn;
    const width = viewer.body.clientWidth - 24;  // marges du corps
    const ratio = window.devicePixelRatio || 1;
    const pages = [];
    for (let n = 1; n <= doc.numPages; n++) {
      const page = await doc.getPage(n);
      const scale = (width / page.getViewport({ scale: 1 }).width) * ratio;
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement("canvas");
      canvas.className = "float-panel__page";
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      const ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      await page.render({ canvasContext: ctx, viewport }).promise;
      if (mine !== drawn || !doc) return;  // redessin ou fermeture entre-temps
      pages.push(canvas);
    }
    viewer.body.replaceChildren(...pages);
  }

  // PDF généré par le serveur ; en cas d'échec, il répond en JSON {error}.
  async function fetchPdf(url) {
    const resp = await fetch(url);
    if (resp.ok && (resp.headers.get("Content-Type") || "").includes("pdf")) return resp.arrayBuffer();
    let error = resp.statusText || "réponse inattendue du serveur";
    try {
      error = (await resp.json()).error || error;
    } catch (e) { /* pas du JSON */ }
    throw new Error(error);
  }

  // {title, file} pour un fichier choisi, {title, url} pour un PDF du serveur.
  async function show({ title, file, url }) {
    panel();
    reset();
    const mine = shown;
    if (file) objectUrl = URL.createObjectURL(file);
    viewer.open({ title, href: objectUrl || url });
    message(url ? "Génération du PDF…" : "Chargement…");
    try {
      if (file && !(file.type === "application/pdf" || /\.pdf$/i.test(file.name))) {
        const img = document.createElement("img");
        img.className = "float-panel__page";
        img.alt = title;
        img.src = objectUrl;
        viewer.body.replaceChildren(img);
        return;
      }
      const pdfjsLib = await waitForPdfJs(8000);
      if (!pdfjsLib) throw new Error("PDF.js ne s'est pas chargé (connexion ?)");
      const data = file ? await file.arrayBuffer() : await fetchPdf(url);
      if (mine !== shown) return;
      const loaded = await pdfjsLib.getDocument({ data }).promise;
      if (mine !== shown) {
        loaded.destroy();
        return;
      }
      doc = loaded;
      await draw();
    } catch (e) {
      if (mine === shown) message("Affichage impossible : " + e.message, true);
    }
  }

  // « Aperçu PDF » : le panneau plutôt qu'un nouvel onglet. Ctrl/⌘-clic ou
  // clic du milieu gardent le lien ordinaire.
  document.addEventListener("click", (e) => {
    const link = e.target.closest && e.target.closest("a[data-pdf-preview]");
    if (!link || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    e.preventDefault();
    show({ title: link.dataset.pdfTitle || "Aperçu PDF", url: link.href });
  });

  return { show };
})();
