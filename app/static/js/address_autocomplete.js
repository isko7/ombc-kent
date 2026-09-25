// Autocomplétion d'adresse partagée (écrans Clients et Plan de Ramassage).
//
// Deux fournisseurs, choisis par le réglage global « Recherche d'adresse »
// (écran Ordre de mission), que la page transmet en `provider` :
// - "google" : Google Places, via la clé Maps JavaScript API chargée par la
//   page. Les suggestions ne portent pas le détail de l'adresse ; celui-ci
//   n'est demandé (Place Details) que sur le choix de l'utilisateur, et
//   seulement si l'appelant en a besoin.
// - "gouv" (ou repli si Google n'est pas chargé) : Base Adresse Nationale,
//   gratuite et sans clé, qui rend d'emblée voie, code postal et commune.
//
// Le formulaire d'ordre de mission garde sa propre copie (mission_form.js) :
// elle est liée à ses lignes d'arrêts et à la lecture des plans (stops_ocr.js).
window.KentAddress = (function () {
  const BAN_URL = "https://api-adresse.data.gouv.fr/search/";
  let autocompleteService = null;
  let placesService = null;

  function googleReady() {
    return !!(window.google && google.maps && google.maps.places);
  }

  function predictions(query) {
    return new Promise((resolve) => {
      if (!autocompleteService) autocompleteService = new google.maps.places.AutocompleteService();
      autocompleteService.getPlacePredictions(
        { input: query, componentRestrictions: { country: "fr" }, language: "fr" },
        (found) => resolve(found || [])
      );
    });
  }

  // Détail d'un lieu Google : voie, code postal et commune séparés. Un appel
  // par adresse retenue, jamais par frappe au clavier.
  function placeDetails(placeId) {
    return new Promise((resolve) => {
      if (!placesService) placesService = new google.maps.places.PlacesService(document.createElement("div"));
      placesService.getDetails(
        { placeId, fields: ["address_components", "formatted_address"], language: "fr" },
        (place, status) => {
          if (status !== "OK" || !place) { resolve(null); return; }
          const part = (type) => {
            const found = (place.address_components || []).find((c) => c.types.includes(type));
            return found ? found.long_name : "";
          };
          const number = part("street_number");
          const route = part("route");
          resolve({
            street: [number, route].filter(Boolean).join(" ") || part("premise") || place.name || "",
            postcode: part("postal_code"),
            city: part("locality") || part("administrative_area_level_2") || "",
            label: place.formatted_address || "",
          });
        }
      );
    });
  }

  // Liste uniforme : { label, street, postcode, city, details() }.
  // `details()` complète voie / code postal / commune quand le fournisseur
  // ne les donne pas d'avance (Google) ; il rend l'item tel quel sinon.
  async function suggest(query, provider) {
    if (provider === "google" && googleReady()) {
      return (await predictions(query)).slice(0, 5).map((p) => {
        const parts = p.structured_formatting || {};
        const item = {
          label: p.description,
          street: parts.main_text || p.description,
          postcode: "",
          city: (parts.secondary_text || "").split(",")[0].trim(),
          details: async () => Object.assign({}, item, await placeDetails(p.place_id) || {}),
        };
        return item;
      });
    }
    try {
      const resp = await fetch(BAN_URL + "?" + new URLSearchParams({ q: query, limit: "5" }));
      return ((await resp.json()).features || []).map((f) => {
        const props = f.properties;
        const item = {
          label: props.label,
          street: props.name || props.label,
          postcode: props.postcode || "",
          city: props.city || "",
          details: async () => item,
        };
        return item;
      });
    } catch (e) {
      return [];  // hors ligne : la saisie libre reste possible
    }
  }

  function closeAll() {
    document.querySelectorAll(".addr-suggestions").forEach((box) => box.remove());
  }

  // Pose la boîte de suggestions sous `input` (son parent doit être en
  // position relative) et appelle `onPick` avec l'adresse choisie.
  function attach(input, options) {
    const provider = () => (typeof options.provider === "function" ? options.provider() : options.provider);
    let timer = null;

    async function show() {
      const query = input.value.trim();
      closeAll();
      if (query.length < 3) return;
      const items = await suggest(query, provider());
      if (!items.length || document.activeElement !== input) return;
      const box = document.createElement("div");
      box.className = "addr-suggestions";
      items.forEach((item) => {
        const line = document.createElement("div");
        line.className = "addr-suggestion";
        line.textContent = item.label;
        // mousedown plutôt que click : se déclenche avant le blur du champ.
        line.addEventListener("mousedown", (e) => {
          e.preventDefault();
          closeAll();
          options.onPick(item);
        });
        box.appendChild(line);
      });
      input.parentNode.appendChild(box);
    }

    input.addEventListener("input", () => {
      clearTimeout(timer);
      timer = setTimeout(show, 250);
    });
    input.addEventListener("blur", () => setTimeout(closeAll, 150));
    document.addEventListener("click", (e) => {
      if (!e.target.closest(".addr-suggestions")) closeAll();
    });
  }

  return { suggest, attach, close: closeAll, googleReady };
})();
