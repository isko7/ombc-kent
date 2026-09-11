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
// Base Adresse Nationale : gratuite, sans clé, et surtout elle renvoie la
// voie et la commune séparément — ce qui permet de remplir « Adresse » et
// « Ville » d'un seul clic.
const BAN_URL = "https://api-adresse.data.gouv.fr/search/";

function closeSuggestions() {
  document.querySelectorAll(".addr-suggestions").forEach((el) => el.remove());
}

async function showAddressSuggestions(input) {
  const q = input.value.trim();
  closeSuggestions();
  if (q.length < 3) return;

  let features;
  try {
    const resp = await fetch(BAN_URL + "?" + new URLSearchParams({ q, limit: "5" }));
    features = (await resp.json()).features || [];
  } catch (e) {
    return; // hors ligne / API indisponible : on laisse la saisie libre
  }
  if (!features.length || document.activeElement !== input) return;

  const box = document.createElement("div");
  box.className = "addr-suggestions";
  features.forEach((f) => {
    const item = document.createElement("div");
    item.className = "addr-suggestion";
    item.textContent = f.properties.label;
    // mousedown plutôt que click : se déclenche avant le blur de l'input.
    item.addEventListener("mousedown", (e) => {
      e.preventDefault();
      const tr = input.closest("tr");
      input.value = f.properties.name || f.properties.label;
      const cityInput = tr && tr.querySelector('[name="stop_city[]"]');
      if (cityInput) cityInput.value = f.properties.city || "";
      closeSuggestions();
    });
    box.appendChild(item);
  });
  input.parentNode.appendChild(box);
}

// ------------------------------------------------ estimation de durée
async function estimateLeg(button) {
  const form = document.getElementById("mission-form");
  const tr = button.closest("tr");
  const result = tr.querySelector(".estimate-result");
  const label = tr.querySelector('[name="leg_label[]"]').value;
  const parts = label.split(ARROW);
  if (parts.length !== 2) {
    result.textContent = "Libellé attendu : « départ → arrivée »";
    result.className = "estimate-result estimate-result--error";
    return;
  }

  const startInput = tr.querySelector('[name="leg_start_time[]"]');
  const body = new FormData();
  body.append("from", parts[0].trim());
  body.append("to", parts[1].trim());
  body.append("start_time", startInput.value.trim());
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
    let text = `≈ ${data.duration} · ${data.km} km`;
    if (data.traffic_min > 0) text += ` (dont ${data.traffic_min} min de trafic)`;
    if (!data.with_traffic_at) text += " · trafic actuel";
    // L'heure de fin n'est calculable que si l'heure de début est saisie.
    const endInput = tr.querySelector('[name="leg_end_time[]"]');
    if (data.end_time && endInput) endInput.value = data.end_time;
    result.textContent = text;
  } catch (e) {
    result.textContent = "Estimation indisponible : " + e.message;
    result.className = "estimate-result estimate-result--error";
  } finally {
    button.disabled = false;
  }
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

document.addEventListener("DOMContentLoaded", () => {
  const addLegBtn = document.getElementById("add-leg-row");
  if (addLegBtn) addLegBtn.addEventListener("click", () => addRow("legs-body", "leg-row-template"));

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
  if (genBtn) genBtn.addEventListener("click", generateLegsFromStops);

  const applyBtn = document.getElementById("apply-vehicle-all");
  if (applyBtn) applyBtn.addEventListener("click", applyVehicleToAllLegs);

  initNewClient();

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
    if (e.target.matches(".row-remove")) removeRow(e.target);
    else if (e.target.matches(".row-up")) moveRow(e.target, -1);
    else if (e.target.matches(".row-down")) moveRow(e.target, 1);
    else if (e.target.matches(".estimate-leg")) estimateLeg(e.target);
    else if (!e.target.closest(".addr-suggestions")) closeSuggestions();
  });

  // Autocomplétion : délégation, pour couvrir aussi les lignes ajoutées
  // après le chargement de la page. `input` ne bulle pas sur `focusout`,
  // d'où les deux écouteurs en phase de capture.
  let addrTimer = null;
  document.body.addEventListener("input", (e) => {
    if (!e.target.matches('[name="stop_address[]"]')) return;
    clearTimeout(addrTimer);
    addrTimer = setTimeout(() => showAddressSuggestions(e.target), 250);
  });
  document.body.addEventListener("focusout", (e) => {
    if (e.target.matches('[name="stop_address[]"]')) setTimeout(closeSuggestions, 150);
  });

  document.body.addEventListener("change", (e) => {
    if (e.target.matches(".leg-vehicle")) toggleRelayDriver(e.target);
    else if (e.target.matches(".relay-driver")) onRelayDriverChange(e.target);
  });
});
