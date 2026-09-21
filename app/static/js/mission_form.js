// Gestion des lignes dynamiques du formulaire "Ordre de mission" :
// tableau des trajets (OM) et tableau des arrêts (BC), + un bouton
// pratique pour pré-remplir les trajets à partir des arrêts saisis.

const DEPOT = "Dépôt KENT";
const ARROW = " → ";

function addRow(tableBodyId, templateId) {
  const tbody = document.getElementById(tableBodyId);
  const tpl = document.getElementById(templateId);
  tbody.appendChild(tpl.content.cloneNode(true));
}

function removeRow(button) {
  const tr = button.closest("tr");
  const rd = tr.querySelector(".relay-driver");
  if (rd) { rd.value = ""; syncRelayRemarks(tr, ""); }
  tr.parentNode.removeChild(tr);
}

// Déplace une ligne d'un cran vers le haut (dir=-1) ou le bas (dir=1).
// L'ordre du DOM = l'ordre enregistré (le back-end lit les champs dans
// l'ordre des lignes), donc rien à faire côté serveur.
function moveRow(button, dir) {
  const tr = button.closest("tr");
  if (dir < 0 && tr.previousElementSibling) {
    tr.parentNode.insertBefore(tr, tr.previousElementSibling);
  } else if (dir > 0 && tr.nextElementSibling) {
    tr.parentNode.insertBefore(tr.nextElementSibling, tr);
  }
}

function fillLegRow(tr, start, end, vehicleId, label) {
  tr.querySelector('[name="leg_start_time[]"]').value = start || "";
  tr.querySelector('[name="leg_end_time[]"]').value = end || "";
  const vSel = tr.querySelector('[name="leg_vehicle_id[]"]');
  if (vSel) vSel.value = vehicleId || "";
  tr.querySelector('[name="leg_label[]"]').value = label || "";
}

function defaultVehicleValue() {
  const sel = document.getElementById("default-vehicle-select");
  return sel ? sel.value : "";
}

function applyVehicleToAllLegs() {
  const v = defaultVehicleValue();
  if (!v) {
    alert("Choisissez d'abord un véhicule dans « Véhicule par défaut ».");
    return;
  }
  document.querySelectorAll('#legs-body select[name="leg_vehicle_id[]"]').forEach((sel) => {
    if (sel.value !== "relais") { sel.value = v; toggleRelayDriver(sel); }
  });
}

// ------------------------------------------------------------ relais
function relayText(option) {
  if (!option || !option.value) return "";
  const fn = (option.dataset.fn || "").trim();
  const ln = (option.dataset.ln || "").trim();
  const tel = (option.dataset.tel || "").trim();
  const who = [fn, ln].filter(Boolean).join(" ");
  return "Relais avec " + who + (tel ? " (" + tel + ")" : "");
}

// Affiche / masque le sélecteur de chauffeur de relais selon le véhicule.
function toggleRelayDriver(vehicleSel) {
  const tr = vehicleSel.closest("tr");
  const rd = tr.querySelector(".relay-driver");
  if (!rd) return;
  if (vehicleSel.value === "relais") {
    rd.hidden = false;
  } else {
    rd.hidden = true;
    if (rd.value) { rd.value = ""; onRelayDriverChange(rd); }
  }
}

// Chauffeur de relais choisi : renseigne le libellé du trajet et ajoute
// une ligne aux remarques (en remplaçant la précédente pour cette ligne).
function onRelayDriverChange(rd) {
  const tr = rd.closest("tr");
  const labelInput = tr.querySelector('[name="leg_label[]"]');
  const text = rd.value ? relayText(rd.selectedOptions[0]) : "";
  const prev = tr.dataset.relayText || "";

  if (text) {
    labelInput.value = text;
  } else if (labelInput.value === prev) {
    labelInput.value = "";
  }
  syncRelayRemarks(tr, text, prev);
  tr.dataset.relayText = text;
}

function syncRelayRemarks(tr, text, prev) {
  const remarks = document.querySelector('[name="remarks"]');
  if (!remarks) return;
  prev = prev !== undefined ? prev : (tr.dataset.relayText || "");
  let lines = remarks.value.split("\n");
  if (prev) lines = lines.filter((l) => l.trim() !== prev.trim());
  if (text && !lines.some((l) => l.trim() === text.trim())) lines.push(text);
  remarks.value = lines.join("\n").replace(/\n{3,}/g, "\n\n").replace(/^\n+|\n+$/g, "");
}

// ------------------------------------------- autocomplétion d'adresse
// Deux fournisseurs, choisis par le réglage global de l'écran Réglages
// (/reglages), lu depuis #mission-form[data-address-provider] :
// - "google" (par défaut) : Google Places, via la clé Maps JavaScript API
//   chargée en page (voir mission_form.html). Se replie automatiquement
//   sur la BAN si le script Google n'est pas chargé (clé absente).
// - "gouv" : Base Adresse Nationale, gratuite et sans clé — et surtout
//   elle renvoie la voie et la commune séparément, ce qui permet de
//   remplir « Adresse » et « Ville » d'un seul clic.
const BAN_URL = "https://api-adresse.data.gouv.fr/search/";
let googlePlacesService = null;

function closeSuggestions() {
  document.querySelectorAll(".addr-suggestions").forEach((el) => el.remove());
}

function addressProvider() {
  const form = document.getElementById("mission-form");
  return form ? form.dataset.addressProvider : "gouv";
}

function googleAvailable() {
  return !!(window.google && google.maps && google.maps.places);
}

function googlePlacePredictions(query) {
  return new Promise((resolve) => {
    if (!googleAvailable()) { resolve([]); return; }
    if (!googlePlacesService) googlePlacesService = new google.maps.places.AutocompleteService();
    googlePlacesService.getPlacePredictions(
      { input: query, componentRestrictions: { country: "fr" }, language: "fr" },
      (predictions) => resolve(predictions || [])
    );
  });
}

// Renvoie une liste uniforme {label, name, city}, quel que soit le
// fournisseur — c'est ce que consomme le rendu de la boîte de suggestions.
async function fetchAddressSuggestions(query) {
  if (addressProvider() === "google" && googleAvailable()) {
    const predictions = await googlePlacePredictions(query);
    return predictions.slice(0, 5).map((p) => {
      const sf = p.structured_formatting || {};
      const city = (sf.secondary_text || "").split(",")[0].trim();
      return { label: p.description, name: sf.main_text || p.description, city };
    });
  }
  try {
    const resp = await fetch(BAN_URL + "?" + new URLSearchParams({ q: query, limit: "5" }));
    const features = (await resp.json()).features || [];
    return features.map((f) => ({
      label: f.properties.label,
      name: f.properties.name || f.properties.label,
      city: f.properties.city || "",
    }));
  } catch (e) {
    return []; // hors ligne / API indisponible : on laisse la saisie libre
  }
}

async function showAddressSuggestions(input) {
  const q = input.value.trim();
  closeSuggestions();
  if (q.length < 3) return;

  const items = await fetchAddressSuggestions(q);
  if (!items.length || document.activeElement !== input) return;

  const box = document.createElement("div");
  box.className = "addr-suggestions";
  items.forEach((it) => {
    const item = document.createElement("div");
    item.className = "addr-suggestion";
    item.textContent = it.label;
    // mousedown plutôt que click : se déclenche avant le blur de l'input.
    item.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const tr = input.closest("tr");
      input.value = it.name;
      const cityInput = tr && tr.querySelector('[name="stop_city[]"]');
      if (cityInput) cityInput.value = it.city || "";
      closeSuggestions();
    });
    box.appendChild(item);
  });
  input.parentNode.appendChild(box);
}

// ------------------------------------------------ estimation de durée
// 2 boutons indépendants par ligne de trajet, chacun son fournisseur —
// TomTom (côté serveur, clé jamais exposée) et Google Maps (côté
// navigateur, via la clé Maps JavaScript API). Affichage seul dans les
// deux cas : les heures saisies (leg_start_time/leg_end_time), donc
// l'amplitude / la conduite / la pause du récap, ne sont jamais modifiées
// par un clic sur « Estimer ».
const DEPOT_FOLD = "depot kent";

function foldPlace(text) {
  return (text || "").trim().toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
}

// Même règle que routing.normalize_place() côté serveur : « Dépôt KENT »
// n'est pas une adresse géocodable, on lui substitue celle de l'entreprise.
function normalizePlaceForGoogle(text) {
  const place = (text || "").trim();
  if (foldPlace(place) === DEPOT_FOLD) {
    const form = document.getElementById("mission-form");
    return (form && form.dataset.depotAddress) || place;
  }
  return place;
}

function splitLegLabel(tr, result) {
  const label = tr.querySelector('[name="leg_label[]"]').value;
  const parts = label.split(ARROW);
  if (parts.length !== 2 || !parts[0].trim() || !parts[1].trim()) {
    result.textContent = "Libellé attendu : « départ → arrivée »";
    result.className = "estimate-result estimate-result--error";
    return null;
  }
  return [parts[0].trim(), parts[1].trim()];
}

function formatDurationJs(seconds) {
  const minutes = Math.round(seconds / 60);
  const h = Math.floor(minutes / 60), m = minutes % 60;
  return h ? `${h} h ${String(m).padStart(2, "0")}` : `${m} min`;
}

function addMinutesToHHMM(startMinutes, deltaSeconds) {
  const total = startMinutes + Math.round(deltaSeconds / 60);
  const norm = ((total % 1440) + 1440) % 1440;
  return `${String(Math.floor(norm / 60)).padStart(2, "0")}:${String(norm % 60).padStart(2, "0")}`;
}

// Date de départ pour le calcul de trafic : celle saisie si elle est dans
// le futur (mission_date + start_time, ou end_time à défaut), sinon "now"
// (trafic courant) — même repli que _datetime_param() côté serveur.
function computeDepartureDate(missionDate, time) {
  const now = new Date();
  const mins = parseHHMM(time);
  if (!missionDate || mins == null) return { date: now, scheduled: false };
  const d = new Date(missionDate + "T00:00:00");
  d.setMinutes(d.getMinutes() + mins);
  return d > now ? { date: d, scheduled: true } : { date: now, scheduled: false };
}

async function estimateLegTomtom(button, tr, result) {
  const parts = splitLegLabel(tr, result);
  if (!parts) return;
  const form = document.getElementById("mission-form");

  const body = new FormData();
  body.append("from", parts[0]);
  body.append("to", parts[1]);
  body.append("start_time", tr.querySelector('[name="leg_start_time[]"]').value.trim());
  body.append("end_time", tr.querySelector('[name="leg_end_time[]"]').value.trim());
  const missionDate = document.querySelector('[name="mission_date"]');
  body.append("mission_date", missionDate ? missionDate.value : "");

  result.className = "estimate-result";
  result.textContent = "Calcul…";
  button.disabled = true;
  try {
    const resp = await fetch(form.dataset.estimateUrl, { method: "POST", body });
    const data = await resp.json();
    if (!resp.ok || !data.ok) {
      result.textContent = data.error || "Estimation indisponible.";
      result.className = "estimate-result estimate-result--error";
      return;
    }
    let text = `TomTom ≈ ${data.duration}`;
    if (data.arrival_time) text += ` (arrivée estimée ${data.arrival_time})`;
    else if (data.departure_time) text += ` (départ estimé ${data.departure_time})`;
    text += ` · ${data.km} km`;
    if (data.traffic_min > 0) text += ` (dont ${data.traffic_min} min de trafic)`;
    if (!data.with_traffic_at) text += " · trafic actuel";
    result.textContent = text;
    tr.dataset.estKm = String(data.km);
  } catch (e) {
    result.textContent = "Estimation indisponible : " + e.message;
    result.className = "estimate-result estimate-result--error";
  } finally {
    button.disabled = false;
    scheduleLegsSummaryUpdate();
  }
}

function estimateLegGoogle(button, tr, result) {
  const parts = splitLegLabel(tr, result);
  if (!parts) return;
  if (!googleAvailable() || !google.maps.DistanceMatrixService) {
    result.textContent = "Clé Google Maps absente : renseignez GOOGLE_MAPS_API_KEY.";
    result.className = "estimate-result estimate-result--error";
    return;
  }

  const origin = normalizePlaceForGoogle(parts[0]);
  const destination = normalizePlaceForGoogle(parts[1]);
  const startTime = tr.querySelector('[name="leg_start_time[]"]').value.trim();
  const endTime = tr.querySelector('[name="leg_end_time[]"]').value.trim();
  const missionDateInput = document.querySelector('[name="mission_date"]');
  const missionDate = missionDateInput ? missionDateInput.value : "";
  const { date: departure, scheduled } = computeDepartureDate(missionDate, startTime || endTime);

  result.className = "estimate-result";
  result.textContent = "Calcul…";
  button.disabled = true;
  new google.maps.DistanceMatrixService().getDistanceMatrix(
    {
      origins: [origin],
      destinations: [destination],
      travelMode: google.maps.TravelMode.DRIVING,
      drivingOptions: { departureTime: departure, trafficModel: google.maps.TrafficModel.BEST_GUESS },
      unitSystem: google.maps.UnitSystem.METRIC,
    },
    (response, status) => {
      button.disabled = false;
      if (status !== "OK") {
        result.textContent = "Estimation indisponible (" + status + ").";
        result.className = "estimate-result estimate-result--error";
        return;
      }
      const el = response.rows[0] && response.rows[0].elements[0];
      if (!el || el.status !== "OK") {
        result.textContent = "Itinéraire introuvable.";
        result.className = "estimate-result estimate-result--error";
        return;
      }
      const durationInfo = el.duration_in_traffic || el.duration;
      const km = Math.round(el.distance.value / 1000);
      const startMinutes = parseHHMM(startTime), endMinutes = parseHHMM(endTime);
      let text = `Maps ≈ ${formatDurationJs(durationInfo.value)}`;
      if (startMinutes != null) text += ` (arrivée estimée ${addMinutesToHHMM(startMinutes, durationInfo.value)})`;
      else if (endMinutes != null) text += ` (départ estimé ${addMinutesToHHMM(endMinutes, -durationInfo.value)})`;
      text += ` · ${km} km`;
      if (el.duration_in_traffic) {
        const trafficMin = Math.round((el.duration_in_traffic.value - el.duration.value) / 60);
        if (trafficMin > 0) text += ` (dont ${trafficMin} min de trafic)`;
      }
      if (!scheduled) text += " · trafic actuel";
      result.textContent = text;
      scheduleLegsSummaryUpdate();
    }
  );
}

function estimateLeg(button) {
  const tr = button.closest("tr");
  const result = tr.querySelector(".estimate-result");
  if (button.dataset.provider === "google") estimateLegGoogle(button, tr, result);
  else estimateLegTomtom(button, tr, result);
}

// -------------------------------------------- récap Trajets (km / temps)
// Heures de conduite + amplitude : calculées tout de suite depuis les
// heures déjà saisies. Kilomètres : pas stockés en base (seule la mini
// estimation par ligne les connaît), donc on interroge l'API d'estimation
// pour chaque ligne « départ → arrivée » valide, avec un petit cache par
// ligne (tr.dataset.estKey/estKm) pour ne pas re-appeler à chaque frappe.
function parseHHMM(value) {
  // Tolère 'h' en plus de ':' : le champ est du texte libre, et certaines
  // heures sont saisies "11h00" (format affiché partout ailleurs) plutôt
  // que "11:00" (ce que routing.js/add_minutes tolèrent déjà côté serveur).
  const m = (value || "").trim().match(/^(\d{1,2})\s*[:hH]\s*(\d{2})$/);
  return m ? parseInt(m[1], 10) * 60 + parseInt(m[2], 10) : null;
}

function formatHoursMinutes(minutes) {
  if (minutes == null || isNaN(minutes)) return "—";
  const h = Math.floor(minutes / 60);
  const m = Math.round(minutes % 60);
  return `${h}h${String(m).padStart(2, "0")}`;
}

// Ecart entre 2 heures-du-jour en minutes, modulo 24h : gère les missions de
// nuit qui passent minuit (ex. 19h00 -> 02h30 = 7h30, pas -16h30). Même
// règle que legs_time_summary() côté serveur (utils.py).
function minutesBetween(startMinutes, endMinutes) {
  return ((endMinutes - startMinutes) % 1440 + 1440) % 1440;
}

function updateLegsTimeSummary() {
  // Amplitude = 1re heure de début valide -> dernière heure de fin valide,
  // dans l'ordre des lignes (comme service_time_range() côté serveur) —
  // pas un min/max numérique, qui se trompe dès qu'une mission passe minuit.
  let firstStart = null, lastEnd = null, drivingMinutes = 0;
  document.querySelectorAll("#legs-body tr").forEach((tr) => {
    const start = parseHHMM(tr.querySelector('[name="leg_start_time[]"]').value);
    const end = parseHHMM(tr.querySelector('[name="leg_end_time[]"]').value);
    if (start != null && end != null) {
      if (firstStart == null) firstStart = start;
      lastEnd = end;
    }
    const vSel = tr.querySelector('[name="leg_vehicle_id[]"]');
    const isDriving = vSel && vSel.value && vSel.value !== "relais";
    if (isDriving && start != null && end != null) {
      drivingMinutes += minutesBetween(start, end);
    }
  });
  const amplitude = (firstStart != null && lastEnd != null) ? minutesBetween(firstStart, lastEnd) : null;
  // Pause = amplitude - conduite : le reste du temps de service qui n'est
  // pas passé à conduire (attente, relais...), pas une saisie séparée.
  const pause = amplitude != null ? Math.max(0, amplitude - drivingMinutes) : null;
  const drivingEl = document.getElementById("legs-summary-driving");
  const pauseEl = document.getElementById("legs-summary-pause");
  const amplitudeEl = document.getElementById("legs-summary-amplitude");
  if (drivingEl) drivingEl.textContent = formatHoursMinutes(drivingMinutes);
  if (pauseEl) pauseEl.textContent = formatHoursMinutes(pause);
  if (amplitudeEl) amplitudeEl.textContent = formatHoursMinutes(amplitude);
}

async function estimateLegKm(tr) {
  const label = tr.querySelector('[name="leg_label[]"]').value;
  const parts = label.split(ARROW);
  if (parts.length !== 2) return null;
  const from = parts[0].trim();
  const to = parts[1].trim();
  if (!from || !to) return null;
  const start = tr.querySelector('[name="leg_start_time[]"]').value.trim();
  const end = tr.querySelector('[name="leg_end_time[]"]').value.trim();

  const key = `${from}|${to}|${start}|${end}`;
  if (tr.dataset.estKey === key) {
    return tr.dataset.estKm ? Number(tr.dataset.estKm) : null;
  }

  const form = document.getElementById("mission-form");
  const missionDate = document.querySelector('[name="mission_date"]');
  const body = new FormData();
  body.append("from", from);
  body.append("to", to);
  body.append("start_time", start);
  body.append("end_time", end);
  body.append("mission_date", missionDate ? missionDate.value : "");

  try {
    const resp = await fetch(form.dataset.estimateUrl, { method: "POST", body });
    const data = await resp.json();
    tr.dataset.estKey = key;
    tr.dataset.estKm = (resp.ok && data.ok) ? String(data.km) : "";
    return (resp.ok && data.ok) ? data.km : null;
  } catch (e) {
    tr.dataset.estKey = key;
    tr.dataset.estKm = "";
    return null;
  }
}

let legsKmRequestToken = 0;
async function updateLegsKmTotal() {
  const token = ++legsKmRequestToken;
  const rows = Array.from(document.querySelectorAll("#legs-body tr"));
  const results = await Promise.all(rows.map(estimateLegKm));
  if (token !== legsKmRequestToken) return; // une saisie plus récente a relancé le calcul
  const el = document.getElementById("legs-summary-km");
  if (!el) return;
  let total = 0, known = 0;
  results.forEach((km) => { if (km != null) { total += km; known += 1; } });
  el.textContent = known > 0 ? `${Math.round(total)} km` : "—";
}

let legsSummaryTimer = null;
function scheduleLegsSummaryUpdate() {
  updateLegsTimeSummary();
  clearTimeout(legsSummaryTimer);
  legsSummaryTimer = setTimeout(updateLegsKmTotal, 600);
}

// -------------------------------------- recherche d'adresse (dropdown)
// Réglage global (table app_settings), sauvegardé en AJAX dès le
// changement — pas besoin d'enregistrer toute la mission pour qu'il
// prenne effet. Met aussi à jour data-address-provider immédiatement,
// pour que l'autocomplétion des arrêts en tienne compte sans recharger.
function initAddressProviderToggle() {
  const select = document.getElementById("address-provider-select");
  const status = document.getElementById("address-provider-status");
  const form = document.getElementById("mission-form");
  if (!select || !form) return;

  select.addEventListener("change", async () => {
    if (status) status.textContent = "Enregistrement…";
    try {
      const body = new FormData();
      body.append("address_search_provider", select.value);
      const resp = await fetch(form.dataset.addressProviderUrl, { method: "POST", body });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        if (status) status.textContent = data.error || "Échec de l'enregistrement.";
        return;
      }
      form.dataset.addressProvider = data.address_search_provider;
      if (status) {
        status.textContent = "Enregistré ✓";
        setTimeout(() => { status.textContent = ""; }, 2000);
      }
    } catch (e) {
      if (status) status.textContent = "Échec de l'enregistrement : " + e.message;
    }
  });
}

// ------------------------------------------------ création de client
// Crée un client sans quitter le formulaire de mission, puis l'ajoute au
// menu déroulant et le sélectionne.
function initNewClient() {
  const box = document.getElementById("new-client-box");
  const toggle = document.getElementById("new-client-toggle");
  const select = document.getElementById("client-select");
  if (!box || !toggle || !select) return;

  const msg = document.getElementById("nc-msg");
  const fields = {
    name: document.getElementById("nc-name"),
    address: document.getElementById("nc-address"),
    postal_code: document.getElementById("nc-postal-code"),
    city: document.getElementById("nc-city"),
    phone: document.getElementById("nc-phone"),
  };

  const close = () => {
    box.hidden = true;
    msg.textContent = "";
    Object.values(fields).forEach((f) => { f.value = ""; });
  };

  toggle.addEventListener("click", (e) => {
    e.preventDefault();
    box.hidden = !box.hidden;
    if (!box.hidden) fields.name.focus();
  });
  document.getElementById("nc-cancel").addEventListener("click", close);

  document.getElementById("nc-save").addEventListener("click", async () => {
    if (!fields.name.value.trim()) {
      msg.textContent = "Le nom du client est obligatoire.";
      fields.name.focus();
      return;
    }
    const body = new FormData();
    Object.entries(fields).forEach(([k, f]) => body.append(k, f.value.trim()));
    msg.textContent = "Création…";
    try {
      const resp = await fetch(box.dataset.url, { method: "POST", body });
      const data = await resp.json();
      if (!resp.ok || !data.ok) {
        msg.textContent = data.error || "Échec de la création.";
        return;
      }
      const opt = document.createElement("option");
      opt.value = data.id;
      opt.textContent = data.name;
      select.appendChild(opt);
      select.value = data.id;
      close();
    } catch (e) {
      msg.textContent = "Échec de la création : " + e.message;
    }
  });
}

// ---------------------------------------------------- génération legs
function generateLegsFromStops() {
  const stopRows = Array.from(document.querySelectorAll("#stops-body tr"));
  const stops = stopRows.map((tr) => ({
    time: tr.querySelector('[name="stop_time[]"]').value,
    address: tr.querySelector('[name="stop_address[]"]').value,
    city: tr.querySelector('[name="stop_city[]"]').value,
  })).filter((s) => s.address || s.city);

  if (stops.length === 0) {
    alert("Ajoutez d'abord au moins un arrêt (prise en charge / dépose).");
    return;
  }

  const legsBody = document.getElementById("legs-body");
  legsBody.innerHTML = "";
  const veh = defaultVehicleValue();
  // Ville puis adresse.
  const label = (s) => (s.city && s.address ? `${s.city}, ${s.address}` : (s.city || s.address));
  const first = stops[0];
  const last = stops[stops.length - 1];

  const add = (start, end, vehicleId, lbl) => {
    addRow("legs-body", "leg-row-template");
    fillLegRow(legsBody.lastElementChild, start, end, vehicleId, lbl);
  };

  // Prise / fin de service : heures laissées vides, c'est le chauffeur qui
  // les renseigne (elles ne se déduisent pas des arrêts).
  add("", "", veh, `Prise de service - ${DEPOT}`);
  add("", first.time, veh, `${DEPOT}${ARROW}${label(first)}`);
  for (let i = 0; i < stops.length - 1; i++) {
    add(stops[i].time, stops[i + 1].time, veh, `${label(stops[i])}${ARROW}${label(stops[i + 1])}`);
  }
  add(last.time, "", veh, `${label(last)}${ARROW}${DEPOT}`);
  add("", "", veh, `Fin de service - ${DEPOT}`);
}

// Répercute la date de la mission sur tous les arrêts (BC) existants,
// pour éviter d'avoir à la corriger ligne par ligne.
function syncStopDates(value) {
  document.querySelectorAll('#stops-body [name="stop_date[]"]').forEach((input) => {
    input.value = value;
  });
}

document.addEventListener("DOMContentLoaded", () => {
  const missionDateInput = document.querySelector('[name="mission_date"]');
  if (missionDateInput) {
    missionDateInput.addEventListener("change", () => syncStopDates(missionDateInput.value));
  }

  const addLegBtn = document.getElementById("add-leg-row");
  if (addLegBtn) addLegBtn.addEventListener("click", () => {
    addRow("legs-body", "leg-row-template");
    scheduleLegsSummaryUpdate();
  });

  const addStopBtn = document.getElementById("add-stop-row");
  if (addStopBtn) addStopBtn.addEventListener("click", () => {
    addRow("stops-body", "stop-row-template");
    // La date du gabarit est figée au chargement de la page (souvent vide
    // sur une mission neuve) : on la reprend depuis le champ Date de la
    // mission au moment de l'ajout, pour avoir la valeur à jour.
    const tr = document.getElementById("stops-body").lastElementChild;
    const dateInput = tr && tr.querySelector('[name="stop_date[]"]');
    const missionDate = document.querySelector('[name="mission_date"]');
    if (dateInput && missionDate && missionDate.value) dateInput.value = missionDate.value;
  });

  const genBtn = document.getElementById("generate-legs-btn");
  if (genBtn) genBtn.addEventListener("click", () => {
    generateLegsFromStops();
    scheduleLegsSummaryUpdate();
  });

  const applyBtn = document.getElementById("apply-vehicle-all");
  if (applyBtn) applyBtn.addEventListener("click", () => {
    applyVehicleToAllLegs();
    scheduleLegsSummaryUpdate();
  });

  initNewClient();
  initAddressProviderToggle();

  // Init : afficher les sélecteurs de relais déjà actifs et mémoriser
  // leur texte pour la synchro des remarques.
  document.querySelectorAll("#legs-body tr").forEach((tr) => {
    const v = tr.querySelector(".leg-vehicle");
    const rd = tr.querySelector(".relay-driver");
    if (v && v.value === "relais" && rd) {
      rd.hidden = false;
      if (rd.value) tr.dataset.relayText = relayText(rd.selectedOptions[0]);
    }
  });

  document.body.addEventListener("click", (e) => {
    if (e.target.matches(".row-remove")) {
      removeRow(e.target);
      scheduleLegsSummaryUpdate();
    } else if (e.target.matches(".row-up")) moveRow(e.target, -1);
    else if (e.target.matches(".row-down")) moveRow(e.target, 1);
    else if (e.target.matches(".estimate-leg")) estimateLeg(e.target);
    else if (!e.target.closest(".addr-suggestions")) closeSuggestions();
  });

  // Autocomplétion : délégation, pour couvrir aussi les lignes ajoutées
  // après le chargement de la page. `input` ne bulle pas sur `focusout`,
  // d'où les deux écouteurs en phase de capture.
  let addrTimer = null;
  document.body.addEventListener("input", (e) => {
    if (e.target.matches('[name="stop_address[]"]')) {
      clearTimeout(addrTimer);
      addrTimer = setTimeout(() => showAddressSuggestions(e.target), 250);
    } else if (e.target.matches(
      '#legs-body [name="leg_start_time[]"], #legs-body [name="leg_end_time[]"], #legs-body [name="leg_label[]"]'
    )) {
      scheduleLegsSummaryUpdate();
    }
  });
  document.body.addEventListener("focusout", (e) => {
    if (e.target.matches('[name="stop_address[]"]')) setTimeout(closeSuggestions, 150);
  });

  document.body.addEventListener("change", (e) => {
    if (e.target.matches(".leg-vehicle")) {
      toggleRelayDriver(e.target);
      scheduleLegsSummaryUpdate();
    } else if (e.target.matches(".relay-driver")) onRelayDriverChange(e.target);
  });

  // Récap Trajets à jour dès le chargement (missions existantes).
  scheduleLegsSummaryUpdate();
});
