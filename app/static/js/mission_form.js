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

// Applique le "véhicule par défaut" à toutes les lignes de trajet.
// Les lignes marquées (relais) sont laissées telles quelles.
function applyVehicleToAllLegs() {
  const v = defaultVehicleValue();
  if (!v) {
    alert("Choisissez d'abord un véhicule dans « Véhicule par défaut ».");
    return;
  }
  document.querySelectorAll('#legs-body select[name="leg_vehicle_id[]"]').forEach((sel) => {
    if (sel.value !== "relais") sel.value = v;
  });
}

// Construit une proposition de trajets OM à partir des arrêts BC déjà
// saisis : prise de service -> Dépôt vers 1er arrêt -> segments entre
// arrêts -> dernier arrêt vers Dépôt -> fin de service. L'utilisateur
// garde la main pour ajouter des pauses/relais ou ajuster les libellés.
function generateLegsFromStops() {
  const stopRows = Array.from(document.querySelectorAll("#stops-body tr"));
  const stops = stopRows.map((tr) => ({
    time: tr.querySelector('[name="stop_time[]"]').value,
    address: tr.querySelector('[name="stop_address[]"]').value,
    city: tr.querySelector('[name="stop_city[]"]').value,
  })).filter((s) => s.address);

  if (stops.length === 0) {
    alert("Ajoutez d'abord au moins un arrêt (prise en charge / dépose).");
    return;
  }

  const legsBody = document.getElementById("legs-body");
  legsBody.innerHTML = "";
  const veh = defaultVehicleValue();
  const label = (s) => (s.city ? `${s.address}, ${s.city}` : s.address);
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

  document.body.addEventListener("click", (e) => {
    if (e.target.matches(".row-remove")) removeRow(e.target);
    else if (e.target.matches(".row-up")) moveRow(e.target, -1);
    else if (e.target.matches(".row-down")) moveRow(e.target, 1);
  });
});
