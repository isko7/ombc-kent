// Lecture des arrêts (Billet Collectif) sur la page choisie d'une pièce
// jointe — formulaire OM uniquement (voir missions/_attachments.html).
//
// Deux sources, dans cet ordre :
// - le texte du PDF, quand il en contient vraiment : exact et immédiat ;
// - sinon l'OCR de la page rendue en image (Tesseract.js). C'est le cas des
//   scans, et des PDF « imprimés » (Microsoft Print to PDF) où le texte est
//   dessiné plutôt qu'écrit. L'OCR tourne dans le navigateur : rien n'est
//   envoyé à un service extérieur, seul le moteur est téléchargé, au
//   premier usage.
//
// Fonctions reprises d'ailleurs : addRow, balancePassengerCounts et la
// recherche d'adresse (fetchAddressSuggestions, addressProvider,
// googleAvailable) de mission_form.js ; waitForPdfJs de pdf_viewer.js.
(function () {
  const box = document.querySelector("[data-stops-ocr]");
  const fileInput = document.getElementById("attach-file");
  if (!box || !fileInput) return;

  const runBtn = box.querySelector("[data-stops-ocr-run]");
  const status = box.querySelector("[data-stops-ocr-status]");
  const pagesInput = document.getElementById("attach-pages");

  const TESSERACT_URL = "https://cdn.jsdelivr.net/npm/tesseract.js@5.1.1/dist/tesseract.min.js";
  // Page rendue à ~180 dpi : texte net pour l'OCR, lu en une à deux secondes.
  const RENDER_SCALE = 2.5;

  function say(text, isError) {
    status.textContent = text;
    status.classList.toggle("is-error", !!isError);
  }

  const pad = (n) => String(n).padStart(2, "0");
  // Sans accents ni casse : « Août » -> « aout ».
  const fold = (text) => text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();

  fileInput.addEventListener("attachment-file", () => {
    box.hidden = false;
    say("");
  });

  // ------------------------------------------------------ pages à lire
  // Pour chaque page : les mots de son texte (vide s'il n'y en a pas) et
  // de quoi la rendre en image pour l'OCR, seulement si besoin. Mots au
  // format de Tesseract : {text, bbox: {x0, y0, x1, y1}}, en pixels.
  async function readSources(file) {
    const isPdf = file.type === "application/pdf" || /\.pdf$/i.test(file.name);
    if (!isPdf) return { sources: [{ words: [], image: async () => file }], close() {} };
    const pdfjsLib = await waitForPdfJs(5000);
    if (!pdfjsLib) throw new Error("PDF.js ne s'est pas chargé (connexion ?)");
    const pdf = await pdfjsLib.getDocument({ data: await file.arrayBuffer() }).promise;
    const chosen = (pagesInput.value ? pagesInput.value.split(",").map(Number) : [1])
      .filter((n) => n >= 1 && n <= pdf.numPages);
    const sources = [];
    for (const n of chosen) {
      const page = await pdf.getPage(n);
      const viewport = page.getViewport({ scale: RENDER_SCALE });
      sources.push({
        words: await textWords(pdfjsLib, page, viewport),
        image: () => renderPage(page, viewport),
      });
    }
    return { sources, close: () => pdf.destroy() };
  }

  // Texte d'une page de PDF. Un morceau de texte peut contenir plusieurs
  // mots : leur position est estimée au prorata des caractères.
  async function textWords(pdfjsLib, page, viewport) {
    const words = [];
    for (const item of (await page.getTextContent()).items) {
      if (!item.str || !item.str.trim()) continue;
      const [, , c, d, x, y] = pdfjsLib.Util.transform(viewport.transform, item.transform);
      const height = Math.hypot(c, d);
      const perChar = (item.width * viewport.scale) / item.str.length;
      for (const m of item.str.matchAll(/\S+/g)) {
        const x0 = x + m.index * perChar;
        words.push({ text: m[0], bbox: { x0, x1: x0 + m[0].length * perChar, y0: y - height, y1: y } });
      }
    }
    return words;
  }

  async function renderPage(page, viewport) {
    const canvas = document.createElement("canvas");
    canvas.width = viewport.width;
    canvas.height = viewport.height;
    const ctx = canvas.getContext("2d");
    // Fond blanc : une zone transparente serait lue comme du noir.
    ctx.fillStyle = "#fff";
    ctx.fillRect(0, 0, canvas.width, canvas.height);
    await page.render({ canvasContext: ctx, viewport }).promise;
    return canvas;
  }

  // ---------------------------------------------------------------- OCR
  let tesseract = null;
  function loadTesseract() {
    tesseract = tesseract || new Promise((resolve, reject) => {
      const script = document.createElement("script");
      script.src = TESSERACT_URL;
      script.onload = () => resolve(window.Tesseract);
      script.onerror = () => {
        tesseract = null;  // nouvel essai au prochain clic
        reject(new Error("moteur OCR injoignable (connexion ?)"));
      };
      document.head.appendChild(script);
    });
    return tesseract;
  }

  async function ocrWorker(progress) {
    const Tesseract = await loadTesseract();
    say("Chargement du moteur OCR (la première fois, quelques secondes)…");
    return Tesseract.createWorker("fra", 1, {
      logger: (m) => {
        if (m.status === "recognizing text") progress(m.progress);
      },
    });
  }

  // ------------------------------------------------- lecture d'un plan
  // Mots regroupés en lignes, de haut en bas puis de gauche à droite.
  // Recalculé depuis leurs positions plutôt que repris de Tesseract, qui
  // peut ranger l'heure et le lieu dans deux blocs différents.
  function toLines(words) {
    const items = words
      .map((w) => Object.assign({ text: w.text.trim() }, w.bbox))
      .filter((w) => w.text)
      .sort((a, b) => (a.y0 + a.y1) - (b.y0 + b.y1));
    const lines = [];
    for (const w of items) {
      const line = lines[lines.length - 1];
      if (line && (w.y0 + w.y1) / 2 <= line.y1) {
        line.words.push(w);
        line.y1 = Math.max(line.y1, w.y1);
      } else {
        lines.push({ words: [w], y1: w.y1 });
      }
    }
    lines.forEach((line) => {
      line.words.sort((a, b) => a.x0 - b.x0);
      line.text = line.words.map((w) => w.text).join(" ");
    });
    return lines;
  }

  const TIME = /^([01]?\d|2[0-3])[:hH.]([0-5]\d)$/;
  // « ALLER LE 27/09/2026 », « ALLER LE 30 SEPTEMBRE 2026 »,
  // « Retour le 1er octobre 2026 ».
  const WHEN = /\b(aller|retour)\s+le\s+(\d{1,2})(?:er)?(?:\s*[/.-]\s*(\d{1,2})\s*[/.-]\s*|\s+([^\s\d]+)\s+)(\d{4})/i;
  const MONTHS = ["janvier", "fevrier", "mars", "avril", "mai", "juin", "juillet",
                  "aout", "septembre", "octobre", "novembre", "decembre"];

  // Un plan de ramassage / dépose : par arrêt, « 05:00  LUCE - CHEZ … RUE »,
  // la fin de l'adresse au besoin à la ligne, les voyageurs, puis
  // « 1 personne ». L'arrêt du rendez-vous avec le car principal (« RDV
  // AVEC LE CAR », ou l'aéroport : « 0 personne ») est celui où tout le
  // monde descend (aller) ou monte (retour).
  function parsePage(lines) {
    const text = lines.map((l) => l.text).join("\n");
    const when = text.match(WHEN);
    const plan = text.match(/PLAN\s+DE\s+(RAMASSAGE|D[ÉE]POSE)/i);
    let retour = null;
    if (when) retour = /^retour$/i.test(when[1]);
    else if (plan) retour = !/^ramassage$/i.test(plan[1]);
    const month = when && (when[3] ? Number(when[3]) : MONTHS.indexOf(fold(when[4])) + 1);

    // Hauteur typique d'un mot : l'échelle de la page, quelle qu'en soit la résolution.
    const heights = lines.flatMap((l) => l.words.map((w) => w.y1 - w.y0)).sort((a, b) => a - b);
    const unit = heights[Math.floor(heights.length / 2)] || 20;

    const stops = [];
    let stop = null;
    let placeX = null;  // colonne du lieu, tant que l'adresse peut continuer à la ligne
    for (const line of lines) {
      const [first, second] = line.words;
      const time = second && first.text.match(TIME);
      if (time) {
        stop = { time: `${pad(time[1])}:${time[2]}`, count: null, meeting: false,
                 place: line.words.slice(1).map((w) => w.text).join(" ") };
        stops.push(stop);
        placeX = second.x0;
        continue;
      }
      if (!stop) continue;
      // Le nombre de voyageurs termine la ligne ; il peut partager celle
      // du rendez-vous (« RDV AVEC LE CAR PRINCIPAL  0 personne »).
      const count = line.text.match(/(?:^|\s)(\d+)\s+personnes?$/i);
      const meeting = /\bRDV\b/i.test(line.text);
      if (count || meeting) {
        if (count) stop.count = Number(count[1]);
        if (meeting) stop.meeting = true;
        placeX = null;
        continue;
      }
      // Suite du lieu : une ligne qui commence dans sa colonne ou plus à
      // droite (« AEROPORT » puis « PARIS ORLY T3 » en plus gros).
      if (placeX !== null && first.x0 > placeX - 1.5 * unit) {
        stop.place += " " + line.text;
        continue;
      }
      placeX = null;
    }
    return {
      date: month >= 1 && month <= 12 ? `${when[5]}-${pad(month)}-${pad(when[2])}` : null,
      retour,
      stops,
    };
  }

  // « LUCE - CHEZ MME … » ou « ORLEANS : MEDIATHEQUE… » : la ville, puis
  // l'adresse après le premier tiret ou deux-points détaché.
  function splitPlace(place) {
    const m = place.match(/^(.+?)\s+[-–—:]\s+(.+)$/) || place.match(/^([^:]+?)\s*:\s*(.+)$/);
    return m ? { city: m[1].trim(), address: m[2].trim() } : { city: "", address: place.trim() };
  }

  // Les plans sont en capitales : « 35B RUE DE L'EGLISE » devient
  // « 35B Rue De L'Eglise » — majuscule en tête de chaque mot (et après
  // un trait d'union ou une apostrophe). Laissés tels quels : les mots qui
  // contiennent un chiffre (2A, 35B, T3, 28300) et ceux déjà en minuscules.
  function titleCase(text) {
    return text.replace(/\S+/g, (word) => {
      if (/\d/.test(word) || word !== word.toUpperCase()) return word;
      return word.toLowerCase().split(/([-'’])/)
        .map((part) => part.replace(/\p{L}/u, (c) => c.toUpperCase()))
        .join("");
    });
  }

  // ------------------------------------------- vérification des adresses
  // Chaque adresse lue est cherchée auprès du fournisseur choisi dans
  // « Recherche d'adresse » (Google ou Base Adresse Nationale). Le résultat
  // ne remplace la lecture que s'il désigne la même chose : même commune,
  // même numéro, même voie aux accents, à la casse et aux abréviations près
  // (on gagne l'orthographe officielle : « Lucé », « 11 Rue des Arènes »).
  // Sinon la lecture reste telle quelle — un géocodeur répond presque
  // toujours quelque chose, pas forcément au bon endroit.
  const ABBREVIATIONS = {
    bd: "boulevard", bvd: "boulevard", blvd: "boulevard", av: "avenue", ave: "avenue",
    st: "saint", ste: "sainte", pl: "place", ch: "chemin", che: "chemin", chem: "chemin",
    imp: "impasse", rte: "route", all: "allee", fbg: "faubourg", sq: "square", crs: "cours",
  };
  const STREET_TYPES = new Set([
    "rue", "avenue", "boulevard", "chemin", "place", "impasse", "route", "allee", "quai",
    "cours", "square", "faubourg", "passage", "sentier", "voie", "ruelle", "venelle",
    "promenade", "esplanade", "parvis", "cite", "residence", "lotissement", "hameau",
    "clos", "mail", "montee", "levee", "chaussee", "rond", "carrefour",
  ]);
  const MINOR_WORDS = new Set(["de", "du", "des", "la", "le", "les", "l", "d", "et", "a", "au", "aux"]);

  const keyOf = (word) => {
    const w = fold(word).replace(/[^a-z0-9]/g, "");
    return ABBREVIATIONS[w] || w;
  };
  // Mots qui comptent pour comparer deux noms : sans accents ni petits mots.
  const keyWords = (text) => text.split(/[\s'’-]+/).map(keyOf).filter((w) => w && !MINOR_WORDS.has(w));

  // « Chez Mme Durand 3 Rue De St Ambroise - Grognault » : ce qui précède
  // la voie (« Chez Mme Durand »), la voie avec son numéro, et ce qui suit
  // un tiret (« Grognault »). null sans type de voie reconnaissable.
  function splitAddress(address) {
    const words = address.split(/\s+/);
    const at = words.findIndex((w) => STREET_TYPES.has(keyOf(w)));
    if (at < 0) return null;
    let start = at;
    if (start >= 2 && /^(bis|ter|quater)$/i.test(words[start - 1]) && /^\d+$/.test(words[start - 2])) start -= 2;
    else if (start >= 1 && /^\d+[a-z]?,?$/i.test(words[start - 1])) start -= 1;
    const rest = words.slice(start).join(" ");
    const dash = rest.search(/\s[-–—]\s/);
    return {
      before: words.slice(0, start).join(" ").replace(/[\s,]+$/, ""),
      street: (dash < 0 ? rest : rest.slice(0, dash)).replace(/,$/, ""),
      after: dash < 0 ? "" : rest.slice(dash).replace(/^\s[-–—]\s/, ""),
    };
  }

  // Numéro (« 5bis ») et nom (« chemin tuilerie ») d'une voie.
  function streetKey(street) {
    const m = street.match(/^\s*(\d+)\s*(bis|ter|quater|[a-z](?![a-z]))?\s*(.*)$/i);
    return m ? { number: m[1] + fold(m[2] || ""), name: keyWords(m[3]).join(" ") }
             : { number: "", name: keyWords(street).join(" ") };
  }

  function sameCity(a, b) {
    const key = (city) => keyWords(city.replace(/\d+/g, "")).join(" ");  // sans code postal
    return !!key(a) && key(a) === key(b);
  }

  // Écart toléré : une coquille de lecture (une lettre sur dix environ).
  function editDistance(a, b) {
    let row = Array.from({ length: b.length + 1 }, (_, j) => j);
    for (let i = 1; i <= a.length; i++) {
      const next = [i];
      for (let j = 1; j <= b.length; j++) {
        next[j] = Math.min(row[j] + 1, next[j - 1] + 1, row[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
      }
      row = next;
    }
    return row[b.length];
  }
  function sameStreet(read, found) {
    if (!read.name || (found.number && found.number !== read.number)) return false;
    return editDistance(read.name, found.name) <= Math.max(1, Math.floor(read.name.length / 10));
  }

  // Met à jour l'arrêt (ville, adresse) ; vrai si son adresse a été confirmée.
  async function verifyAddress(stop) {
    if (!stop.city) return false;
    const parts = splitAddress(stop.address);
    const query = `${parts ? parts.street : stop.address} ${stop.city}`;
    const found = (await fetchAddressSuggestions(query)).filter((r) => sameCity(stop.city, r.city));
    if (!found.length) return false;
    stop.city = found[0].city;  // orthographe officielle de la commune
    if (!parts) return false;
    const read = streetKey(parts.street);
    const match = found.find((r) => (r.kind === "housenumber" || r.kind === "street")
                                   && sameStreet(read, streetKey(r.name)));
    if (!match) return false;
    // Voie trouvée sans numéro : on garde celui du document.
    const number = read.number && !streetKey(match.name).number
      ? parts.street.match(/^\s*\d+\s*(?:bis|ter|quater|[a-z](?![a-z]))?/i)[0].trim() + " " : "";
    stop.city = match.city;
    stop.address = [parts.before, number + match.name].filter(Boolean).join(", ")
      + (parts.after ? " - " + parts.after : "");
    return true;
  }

  function providerName() {
    return addressProvider() === "google" && googleAvailable() ? "Google" : "la Base Adresse Nationale";
  }

  // Arrêts du Billet Collectif. Aller (ramassage) : prises en charge, puis
  // dépose de tout le monde au rendez-vous ; retour (dépose) : l'inverse.
  // Sens inconnu : un rendez-vous en tête de liste signe un retour.
  function toStops(page, fallbackDate) {
    const isMeeting = (s) => s.meeting || s.count === 0;
    if (!page.stops.length) return [];
    const retour = page.retour !== null ? page.retour : isMeeting(page.stops[0]);
    const total = page.stops.filter((s) => !isMeeting(s)).reduce((sum, s) => sum + (s.count || 0), 0);
    return page.stops.map((s) => {
      const meeting = isMeeting(s);
      const { city, address } = splitPlace(s.place);
      return {
        type: meeting === retour ? "prise_en_charge" : "depose",
        date: page.date || fallbackDate,
        time: s.time,
        city: titleCase(city),
        address: titleCase(address),
        count: meeting ? total || null : s.count,
      };
    });
  }

  // --------------------------------------------------- tableau des arrêts
  // Des arrêts sont déjà saisis : on demande avant de les remplacer.
  function confirmReplace(count) {
    const typed = Array.from(document.getElementById("stops-body").rows).filter((tr) =>
      ["stop_time[]", "stop_city[]", "stop_address[]"].some((name) => {
        const field = tr.querySelector(`[name="${name}"]`);
        return field && field.value.trim();
      }));
    return !typed.length
      || confirm(`Remplacer les ${typed.length} arrêt(s) déjà saisi(s) par les ${count} arrêts lus sur la page ?`);
  }

  function fillStops(stops) {
    const body = document.getElementById("stops-body");
    body.replaceChildren();
    for (const s of stops) {
      addRow("stops-body", "stop-row-template");
      const tr = body.lastElementChild;
      const set = (name, value) => {
        const field = tr.querySelector(`[name="${name}"]`);
        if (field && value != null && value !== "") field.value = value;
      };
      set("stop_type[]", s.type);
      set("stop_date[]", s.date);
      set("stop_time[]", s.time);
      set("stop_city[]", s.city);
      set("stop_address[]", s.address);
      set("stop_passenger_count[]", s.count);
    }
    // L'arrêt de rendez-vous porte la somme des autres (règle du formulaire).
    balancePassengerCounts();
  }

  // Chaque page : son texte s'il donne des arrêts, sinon l'OCR (moteur
  // chargé une seule fois, et seulement si une page en a besoin).
  async function readPages(sources) {
    const pages = [];
    let worker = null;
    let current = 0;
    const progress = (p) => {
      const which = sources.length > 1 ? ` de la page ${current + 1}/${sources.length}` : "";
      say(`Lecture${which}… ${Math.round(p * 100)} %`);
    };
    try {
      for (; current < sources.length; current++) {
        const source = sources[current];
        let page = source.words.length ? parsePage(toLines(source.words)) : null;
        if (!page || !page.stops.length) {
          worker = worker || await ocrWorker(progress);
          const { data } = await worker.recognize(await source.image());
          page = parsePage(toLines(data.words));
        }
        pages.push(page);
      }
      return pages;
    } finally {
      if (worker) await worker.terminate();
    }
  }

  runBtn.addEventListener("click", async () => {
    const file = fileInput.files[0];
    if (!file) {
      say("Choisissez d'abord un fichier.", true);
      return;
    }
    runBtn.disabled = true;
    let pdf = null;
    try {
      say("Lecture de la page…");
      pdf = await readSources(file);
      if (!pdf.sources.length) throw new Error("aucune page choisie");
      const missionDate = document.querySelector('#mission-form [name="mission_date"]');
      const pages = await readPages(pdf.sources);
      const stops = pages.flatMap((page) => toStops(page, missionDate.value));
      if (!stops.length) {
        say("Aucun arrêt reconnu sur cette page.", true);
        return;
      }
      if (!confirmReplace(stops.length)) {
        say("");
        return;
      }
      say(`Vérification des adresses auprès de ${providerName()}…`);
      const confirmed = (await Promise.all(stops.map((s) => verifyAddress(s).catch(() => false))))
        .filter(Boolean).length;
      fillStops(stops);
      // Mission encore sans date : celle du plan (jamais écrasée sinon).
      const dated = pages.find((page) => page.date);
      if (!missionDate.value && dated) missionDate.value = dated.date;
      const s = confirmed > 1 ? "s" : "";
      say(`${stops.length} arrêts ajoutés, ${confirmed} adresse${s} confirmée${s} par ${providerName()}`
          + " — vérifiez-les dans « Arrêts — Billet Collectif ».");
      document.getElementById("stops-table").scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (e) {
      say("Lecture impossible : " + e.message, true);
    } finally {
      if (pdf) pdf.close();
      runBtn.disabled = false;
    }
  });
})();
