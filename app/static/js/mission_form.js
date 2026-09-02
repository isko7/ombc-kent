// Gestion des lignes dynamiques du formulaire "Ordre de mission" :
// tableau des trajets (OM) et tableau des arrêts (BC), + un bouton
// pratique pour pré-remplir les trajets à partir des arrêts saisis.

function addRow(tableBodyId, templateId) {
  const tbody = document.getElementById(tableBodyId);
  const tpl = document.getElementById(templateId);
  const clone = tpl.content.cloneNode(true);
  tbody.appendChild(clone);
}

function removeRow(button) {
  const tr = button.closest("tr");
  tr.parentNode.removeChild(tr);
}

function fillLegRow(tr, start, end, vehicleId, label) {
  tr.querySelector('[name="leg_start_time[]"]').value = start || "";
  tr.querySelector('[name="leg_end_time[]"]').value = end || "";
  const vSel = tr.querySelector('[name="leg_vehicle_id[]"]');
  if (vSel) vSel.value = vehicleId || "";
  tr.querySelector('[name="leg_label[]"]').value = label || "";
}

// Construit une proposition de trajets OM à partir des arrêts BC déjà
// saisis : "Prise de service" -> segments entre arrêts consécutifs ->
// "Fin de service". L'utilisateur garde la main pour ajouter des pauses
// ou ajuster les libellés ensuite.
function generateLegsFromStops() {
  const stopRows = Array.from(document.querySelectorAll("#stops-body tr"));
  const stops = stopRows.map((tr) => ({
    type: tr.querySelector('[name="stop_type[]"]').value,
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
  const defaultVehicle = document.getElementById("default-vehicle-select")
    ? document.getElementById("default-vehicle-select").value
    : "";

  const label = (s) => s.city ? `${s.address}, ${s.city}` : s.address;

  addRow("legs-body", "leg-row-template");
  fillLegRow(legsBody.lastElementChild, stops[0].time, stops[0].time, defaultVehicle, "Prise de service - Dépôt KENT");

  for (let i = 0; i < stops.length - 1; i++) {
    addRow("legs-body", "leg-row-template");
    fillLegRow(
      legsBody.lastElementChild,
      stops[i].time, stops[i + 1].time, defaultVehicle,
      `${label(stops[i])} \u2192 ${label(stops[i + 1])}`
    );
  }

  const last = stops[stops.length - 1];
  addRow("legs-body", "leg-row-template");
  fillLegRow(legsBody.lastElementChild, last.time, last.time, defaultVehicle, "Fin de service - Dépôt KENT");
}

document.addEventListener("DOMContentLoaded", () => {
  const addLegBtn = document.getElementById("add-leg-row");
  if (addLegBtn) addLegBtn.addEventListener("click", () => addRow("legs-body", "leg-row-template"));

  const addStopBtn = document.getElementById("add-stop-row");
  if (addStopBtn) addStopBtn.addEventListener("click", () => addRow("stops-body", "stop-row-template"));

  const genBtn = document.getElementById("generate-legs-btn");
  if (genBtn) genBtn.addEventListener("click", generateLegsFromStops);

  document.body.addEventListener("click", (e) => {
    if (e.target.matches(".row-remove")) removeRow(e.target);
  });
});
