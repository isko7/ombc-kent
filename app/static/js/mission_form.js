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
  const who = (fn ? fn.charAt(0).toUpperCase() + "." : "") + ln;
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

  add(first.time, first.time, veh, `Prise de service - ${DEPOT}`);
  add("", first.time, veh, `${DEPOT}${ARROW}${label(first)}`);
  for (let i = 0; i < stops.length - 1; i++) {
    add(stops[i].time, stops[i + 1].time, veh, `${label(stops[i])}${ARROW}${label(stops[i + 1])}`);
  }
  add(last.time, "", veh, `${label(last)}${ARROW}${DEPOT}`);
  add(last.time, last.time, veh, `Fin de service - ${DEPOT}`);
}

document.addEventListener("DOMContentLoaded", () => {
  const addLegBtn = document.getElementById("add-leg-row");
  if (addLegBtn) addLegBtn.addEventListener("click", () => addRow("legs-body", "leg-row-template"));

  const addStopBtn = document.getElementById("add-stop-row");
  if (addStopBtn) addStopBtn.addEventListener("click", () => addRow("stops-body", "stop-row-template"));

  const genBtn = document.getElementById("generate-legs-btn");
  if (genBtn) genBtn.addEventListener("click", generateLegsFromStops);

  const applyBtn = document.getElementById("apply-vehicle-all");
  if (applyBtn) applyBtn.addEventListener("click", applyVehicleToAllLegs);

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
  });

  document.body.addEventListener("change", (e) => {
    if (e.target.matches(".leg-vehicle")) toggleRelayDriver(e.target);
    else if (e.target.matches(".relay-driver")) onRelayDriverChange(e.target);
  });
});
