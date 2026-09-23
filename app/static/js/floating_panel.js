// Panneau flottant, non modal : on le consulte sans quitter la page — fiche
// d'une mission liée (linked_missions.js), document agrandi ou aperçu du
// PDF (pdf_viewer.js). Déplaçable par son titre, redimensionnable par son
// coin ; taille et position mémorisées par le navigateur. Sur téléphone,
// le CSS le pose en bas de l'écran, sans position ni taille imposées.
//
// KentFloat.create({name, label, storageKey, ...}) construit le panneau et
// renvoie {panel, body, open({title, href}), close()} ; le contenu va dans
// body.
window.KentFloat = window.KentFloat || (function () {
  const MARGIN = 12;
  const narrow = window.matchMedia("(max-width: 720px)");
  let front = 35;  // z-index du dernier panneau ouvert ou saisi

  function create(options) {
    const opts = Object.assign({
      name: "", label: "", className: "", storageKey: null, widthRatio: 0.45, maxWidth: 640,
      onClose() {}, onResize() {},
    }, options);

    const panel = document.createElement("aside");
    panel.className = ("float-panel " + opts.className).trim();
    panel.dataset.float = opts.name;
    panel.setAttribute("aria-label", opts.label);
    panel.hidden = true;
    panel.innerHTML = `
      <div class="float-panel__head" data-float-drag>
        <span class="float-panel__title" data-float-title></span>
        <a class="float-panel__btn" data-float-open target="_blank" rel="noopener"
           title="Ouvrir dans un nouvel onglet" aria-label="Ouvrir dans un nouvel onglet">↗</a>
        <button type="button" class="float-panel__btn" data-float-close
                title="Fermer" aria-label="Fermer">&times;</button>
      </div>
      <div class="float-panel__body" data-float-body></div>
      <div class="float-panel__resize" data-float-resize aria-hidden="true"></div>`;
    document.body.appendChild(panel);
    const title = panel.querySelector("[data-float-title]");
    const openTab = panel.querySelector("[data-float-open]");

    const toFront = () => { panel.style.zIndex = String(++front); };
    panel.addEventListener("pointerdown", toFront);

    // localStorage peut lever (navigation privée) : le panneau reprend
    // alors sa place par défaut, à droite, sur toute la hauteur.
    function savedGeometry() {
      try {
        const g = JSON.parse(localStorage.getItem(opts.storageKey));
        if (g && ["left", "top", "width", "height"].every((k) => typeof g[k] === "number")) return g;
      } catch (e) { /* rien de mémorisé */ }
      const width = Math.min(opts.maxWidth, Math.round(window.innerWidth * opts.widthRatio));
      return { left: window.innerWidth - width - 20, top: 80, width, height: window.innerHeight - 100 };
    }
    function remember() {
      const r = panel.getBoundingClientRect();
      try {
        localStorage.setItem(opts.storageKey, JSON.stringify(
          { left: r.left, top: r.top, width: r.width, height: r.height }));
      } catch (e) { /* tant pis */ }
    }

    // Le panneau reste entier dans la fenêtre.
    function place(g) {
      const style = panel.style;
      if (narrow.matches) {
        style.left = style.top = style.width = style.height = "";
        return;
      }
      const width = Math.max(320, Math.min(g.width, window.innerWidth - 2 * MARGIN));
      const height = Math.max(240, Math.min(g.height, window.innerHeight - 2 * MARGIN));
      style.left = Math.max(MARGIN, Math.min(g.left, window.innerWidth - width - MARGIN)) + "px";
      style.top = Math.max(MARGIN, Math.min(g.top, window.innerHeight - height - MARGIN)) + "px";
      style.width = width + "px";
      style.height = height + "px";
    }

    // Glisser le titre déplace le panneau, glisser le coin le redimensionne.
    // Pendant le geste, une iframe du contenu ne capte plus la souris
    // (classe is-moving) : elle avalerait sinon le mouvement.
    function onDrag(handle, geometry, resizing) {
      handle.addEventListener("pointerdown", (e) => {
        if (narrow.matches || e.button !== 0 || e.target.closest("a, button")) return;
        e.preventDefault();
        const x = e.clientX;
        const y = e.clientY;
        const start = panel.getBoundingClientRect();
        const move = (ev) => place(geometry(start, ev.clientX - x, ev.clientY - y));
        const end = () => {
          handle.removeEventListener("pointermove", move);
          handle.removeEventListener("pointerup", end);
          handle.removeEventListener("pointercancel", end);
          panel.classList.remove("is-moving");
          remember();
          if (resizing) opts.onResize();
        };
        handle.setPointerCapture(e.pointerId);
        panel.classList.add("is-moving");
        handle.addEventListener("pointermove", move);
        handle.addEventListener("pointerup", end);
        handle.addEventListener("pointercancel", end);
      });
    }
    onDrag(panel.querySelector("[data-float-drag]"), (r, dx, dy) =>
      ({ left: r.left + dx, top: r.top + dy, width: r.width, height: r.height }));
    onDrag(panel.querySelector("[data-float-resize]"), (r, dx, dy) =>
      ({ left: r.left, top: r.top, width: r.width + dx, height: r.height + dy }), true);

    window.addEventListener("resize", () => {
      if (panel.hidden) return;
      place(panel.getBoundingClientRect());
      opts.onResize();
    });

    function open({ title: text, href }) {
      title.textContent = text;
      title.title = text;
      openTab.hidden = !href;
      if (href) openTab.href = href;
      if (panel.hidden) {
        panel.hidden = false;
        place(savedGeometry());
      }
      toFront();
    }
    function close() {
      panel.hidden = true;
      opts.onClose();
    }
    panel.querySelector("[data-float-close]").addEventListener("click", close);

    return { panel, body: panel.querySelector("[data-float-body]"), open, close };
  }

  return { create };
})();
