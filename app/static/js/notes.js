// Bloc-notes personnel : un panneau ancré en bas à droite, volontairement
// PAS une fenêtre modale — il doit rester ouvert pendant qu'on navigue.
//
// L'application est rendue par le serveur : chaque page est un chargement
// complet, le panneau est donc reconstruit à chaque fois. C'est l'état
// (ouvert/replié) qui est mémorisé dans le navigateur et rejoué au
// chargement, ce qui donne l'impression d'un panneau qui ne se ferme pas.
//
// Corollaire : quitter la page ne doit rien perdre. La saisie est
// enregistrée automatiquement après une pause, et un dernier envoi part en
// sendBeacon si on navigue avec des modifications en attente.
(function () {
  const OPEN_KEY = "kent.notes.open";
  const AUTOSAVE_MS = 900;

  const panel = document.getElementById("notes-panel");
  const toggle = document.getElementById("notes-open");
  if (!panel || !toggle) return;

  const text = document.getElementById("notes-text");
  const status = document.getElementById("notes-status");
  const closeBtn = document.getElementById("notes-close");
  const url = panel.dataset.url;

  let saved = text.value;
  let timer = null;

  // localStorage peut lever (navigation privée, cookies bloqués) : le
  // panneau doit marcher quand même, simplement sans mémoire.
  function remember(open) {
    try {
      localStorage.setItem(OPEN_KEY, open ? "1" : "0");
    } catch (e) { /* tant pis */ }
  }
  function wasOpen() {
    try {
      return localStorage.getItem(OPEN_KEY) === "1";
    } catch (e) {
      return false;
    }
  }

  function setStatus(message, isError) {
    status.textContent = message;
    status.classList.toggle("is-error", !!isError);
  }

  function setOpen(open, persist) {
    panel.hidden = !open;
    toggle.classList.toggle("is-active", open);
    toggle.setAttribute("aria-expanded", open ? "true" : "false");
    if (persist !== false) remember(open);
  }

  async function save() {
    const value = text.value;
    if (value === saved) return;
    setStatus("Enregistrement…", false);
    try {
      const body = new FormData();
      body.append("notes", value);
      const resp = await fetch(url, { method: "POST", body });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        setStatus(data.error || "Échec de l'enregistrement.", true);
        return;
      }
      saved = value;
      setStatus("Enregistré ✓", false);
      setTimeout(() => {
        if (status.textContent === "Enregistré ✓") setStatus("", false);
      }, 2000);
    } catch (e) {
      setStatus("Échec de l'enregistrement : " + e.message, true);
    }
  }

  text.addEventListener("input", () => {
    setStatus("Modifié…", false);
    clearTimeout(timer);
    timer = setTimeout(save, AUTOSAVE_MS);
  });

  // Départ vers une autre page avec une saisie en attente : sendBeacon part
  // même pendant le déchargement, contrairement à fetch().
  window.addEventListener("pagehide", () => {
    if (text.value === saved) return;
    try {
      const body = new FormData();
      body.append("notes", text.value);
      navigator.sendBeacon(url, body);
      saved = text.value;
    } catch (e) { /* la sauvegarde auto aura couvert l'essentiel */ }
  });

  toggle.addEventListener("click", () => {
    const open = panel.hidden;
    setOpen(open);
    if (open) text.focus();
  });
  closeBtn.addEventListener("click", () => {
    clearTimeout(timer);
    save();
    setOpen(false);
  });

  // Échap ferme le panneau, mais seulement s'il a le focus : ailleurs dans
  // la page, la touche ne doit pas escamoter des notes qu'on lit.
  panel.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      clearTimeout(timer);
      save();
      setOpen(false);
      toggle.focus();
    }
  });

  setOpen(wasOpen(), false);
})();
