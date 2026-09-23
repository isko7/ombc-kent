// Missions liées — section de la fiche OM et du formulaire (création /
// modification), voir templates/missions/_linked_missions.html.
//
// - Le tableau est rendu ici, depuis le JSON posé dans la page.
// - La fenêtre de sélection charge les missions en fetch (/missions/a-lier,
//   déjà triées par le serveur). Sur la fiche, elle enregistre par un POST
//   classique ; dans le formulaire, elle met à jour des champs cachés,
//   enregistrés avec la mission.
// - Un clic sur le nom d'une mission liée ouvre sa fiche dans un panneau
//   flottant (iframe) : on la consulte sans quitter la page, et dans le
//   formulaire on y recopie ce qui sert. Ctrl/⌘-clic ou clic du milieu :
//   nouvel onglet, comme un lien ordinaire.
(function () {
  const card = document.querySelector("[data-linked-missions]");
  const dialog = document.querySelector("[data-linked-dialog]");
  if (!card || !dialog) return;

  const formMode = card.hasAttribute("data-form-mode");

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }

  // Recherche sans accents ni casse : « creche » trouve « Crèche ».
  function fold(text) {
    return text.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  // --------------------------------------------------------------- tableau
  const table = card.querySelector("[data-linked-table]");
  const tbody = table.querySelector("tbody");
  const empty = card.querySelector("[data-linked-empty]");
  let rows = JSON.parse(card.querySelector("[data-linked-rows]").textContent);

  function renderTable() {
    tbody.textContent = "";
    rows.forEach((r) => {
      const link = el("a");
      link.href = r.url;
      link.appendChild(el("strong", null, r.name));
      link.addEventListener("click", (e) => {
        if (e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
        e.preventDefault();
        openFloat(r);
      });
      const name = el("td");
      name.appendChild(link);
      const date = el("td");
      date.append(el("div", null, r.day), el("div", null, r.date));
      const tr = el("tr");
      tr.append(name, date, el("td", null, r.start), el("td", null, r.end),
                el("td", null, r.driver), el("td", null, r.amplitude));
      tbody.appendChild(tr);
    });
    table.hidden = rows.length === 0;
    empty.hidden = rows.length > 0;
  }

  // Formulaire : la sélection part avec la mission, dans des champs cachés.
  function syncInputs() {
    const box = card.querySelector("[data-linked-inputs]");
    box.textContent = "";
    rows.forEach((r) => {
      const input = el("input");
      input.type = "hidden";
      input.name = "linked_mission_ids[]";
      input.value = r.id;
      box.appendChild(input);
    });
  }

  // ------------------------------------------------- fenêtre de sélection
  const list = dialog.querySelector("[data-linked-list]");
  const filter = dialog.querySelector("[data-linked-filter]");
  const count = dialog.querySelector("[data-linked-count]");
  const submit = dialog.querySelector("[data-linked-submit]");
  let candidates = [];
  let loads = 0;

  // Nom qui fait remonter les missions de même code : celui en cours de
  // saisie dans le formulaire, celui de la mission sur la fiche.
  function currentName() {
    const field = formMode && document.querySelector('#mission-form [name="mission_name"]');
    return field ? field.value : card.dataset.name;
  }

  async function openDialog() {
    const load = ++loads;
    candidates = [];
    filter.value = "";
    count.textContent = "";
    // Tant que la liste n'est pas chargée, valider effacerait tous les
    // liens : le bouton ne s'active qu'une fois les missions affichées.
    submit.disabled = true;
    list.replaceChildren(el("p", "hint", "Chargement…"));
    dialog.showModal();
    const params = new URLSearchParams({ name: currentName() });
    if (card.dataset.exclude) params.set("exclude", card.dataset.exclude);
    try {
      const resp = await fetch(card.dataset.candidatesUrl + "?" + params);
      const data = await resp.json();
      if (!resp.ok || !data.ok) throw new Error(data.error || resp.statusText);
      if (load !== loads) return;  // fenêtre rouverte entre-temps
      candidates = data.missions;
      renderOptions();
      submit.disabled = false;
    } catch (e) {
      if (load !== loads) return;
      list.replaceChildren(el("p", "hint is-error", "Impossible de charger les missions : " + e.message));
    }
  }

  function renderOptions() {
    const selected = new Set(rows.map((r) => r.id));
    const same = candidates.filter((c) => c.same_code);
    const others = candidates.filter((c) => !c.same_code);
    list.replaceChildren();
    if (same.length) list.appendChild(group("Même code que cette mission", same, selected));
    if (others.length) list.appendChild(group(same.length ? "Autres missions" : null, others, selected));
    if (!candidates.length) list.appendChild(el("p", "hint", "Aucune autre mission."));
    updateCount();
  }

  function group(title, missions, selected) {
    const box = el("div", "linked-group");
    if (title) box.appendChild(el("div", "linked-group__title", title));
    missions.forEach((c) => {
      const check = el("input");
      check.type = "checkbox";
      check.name = "linked_mission_ids[]";
      check.value = c.id;
      check.checked = selected.has(c.id);
      const hours = c.start === "—" ? "sans horaire" : c.start + "–" + c.end;
      const text = el("span", "linked-option__text");
      text.append(el("span", "linked-option__name", c.name),
                  el("span", "linked-option__meta", [c.day + " " + c.date, hours, c.driver].join(" · ")));
      const option = el("label", "linked-option");
      option.append(check, text);
      option.dataset.search = fold([c.name, c.day, c.date, c.driver].join(" "));
      box.appendChild(option);
    });
    return box;
  }

  function updateCount() {
    const n = list.querySelectorAll("input:checked").length;
    count.textContent = n ? n + (n > 1 ? " missions sélectionnées" : " mission sélectionnée") : "";
  }

  filter.addEventListener("input", () => {
    const words = fold(filter.value).split(/\s+/).filter(Boolean);
    list.querySelectorAll(".linked-group").forEach((box) => {
      let visible = 0;
      box.querySelectorAll(".linked-option").forEach((option) => {
        option.hidden = !words.every((w) => option.dataset.search.includes(w));
        if (!option.hidden) visible++;
      });
      box.hidden = visible === 0;
    });
  });
  // Entrée dans le filtre ne doit pas valider la sélection.
  filter.addEventListener("keydown", (e) => {
    if (e.key === "Enter") e.preventDefault();
  });
  list.addEventListener("change", updateCount);

  dialog.querySelector("form").addEventListener("submit", (e) => {
    if (!formMode) return;  // fiche : POST normal, la page se recharge
    e.preventDefault();
    const ids = new Set(Array.from(list.querySelectorAll("input:checked"), (c) => Number(c.value)));
    rows = candidates.filter((c) => ids.has(c.id))
      .sort((a, b) => (a.sort < b.sort ? -1 : a.sort > b.sort ? 1 : a.id - b.id));
    renderTable();
    syncInputs();
    dialog.close();
  });

  dialog.querySelectorAll("[data-linked-close]").forEach((btn) => {
    btn.addEventListener("click", () => dialog.close());
  });
  // Clic sur le fond grisé : le formulaire remplit la fenêtre, tout clic
  // qui atteint la <dialog> elle-même est donc hors du contenu.
  dialog.addEventListener("click", (e) => {
    if (e.target === dialog) dialog.close();
  });
  card.querySelector("[data-linked-open]").addEventListener("click", openDialog);

  // ----------------------------------------------------- panneau flottant
  // La fiche de la mission liée, dans une iframe (vue ?embed=1 : sans barre
  // de navigation, en lecture seule).
  const frame = document.createElement("iframe");
  frame.className = "float-panel__frame";
  frame.title = "Fiche de la mission liée";
  const float = KentFloat.create({
    name: "mission", label: "Mission liée", storageKey: "kent.missionFloat",
    onClose: () => { frame.src = "about:blank"; },
  });
  float.body.appendChild(frame);

  function openFloat(r) {
    frame.src = r.embed_url;
    float.open({ title: `${r.name} — ${r.day} ${r.date}`, href: r.url });
  }

  renderTable();
})();
