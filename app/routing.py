"""
Estimation de durée de trajet, pour le bouton « Estimer » des lignes de
trajet du formulaire de mission.

Deux services, chacun choisi pour ce qu'il fait de mieux :

- **Géocodage** : Base Adresse Nationale (api-adresse.data.gouv.fr).
  Gratuite, sans clé, spécialisée sur les adresses françaises. C'est
  aussi elle qui alimente l'autocomplétion des arrêts côté navigateur.
- **Itinéraire** : TomTom Routing API, avec `departAt` et le modèle de
  trafic, donc une durée qui tient compte de l'heure de départ. Appelée
  côté serveur uniquement, pour que la clé n'apparaisse jamais dans le
  navigateur.

Aucune dépendance supplémentaire : urllib de la stdlib, comme le reste
des appels sortants de l'application.
"""
import json
import re
import urllib.parse
import urllib.request
from datetime import datetime
from math import asin, cos, radians, sin, sqrt

from app.config import COMPANY, TOMTOM_API_KEY
from app.utils import _fold, is_depot

BAN_URL = "https://api-adresse.data.gouv.fr/search/"
TOMTOM_ROUTE_URL = "https://api.tomtom.com/routing/1/calculateRoute/{coords}/json"
# Recherche « fuzzy » (produit Search API) plutôt que /geocode (produit
# Geocoding API) : elle trouve aussi les lieux non postaux — aéroports,
# gares — qui sont précisément le cas d'usage de ce repli.
TOMTOM_SEARCH_URL = "https://api.tomtom.com/search/2/search/{query}.json"
TIMEOUT_SECONDS = 12


class RoutingError(Exception):
    pass


def _get_json(url, timeout=TIMEOUT_SECONDS):
    req = urllib.request.Request(url, headers={"User-Agent": "planning-kent/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:200]
        raise RoutingError(f"{e.code} — {detail}") from e
    except Exception as e:
        raise RoutingError(str(e)) from e


def normalize_place(text):
    """Prépare un libellé de trajet pour la BAN.

    - « Dépôt KENT » n'est pas une adresse : on lui substitue celle de
      l'entreprise (COMPANY).
    - les libellés sont au format « VILLE, adresse » (choix d'affichage de
      l'OM) alors que la BAN attend l'ordre naturel « adresse, ville » ;
      sans ce ré-ordonnancement elle se trompe de commune.
    """
    place = (text or "").strip()
    if is_depot(place):
        return f"{COMPANY['address']}, {COMPANY['postal_code']} {COMPANY['city']}"
    if ", " in place:
        city, address = place.split(", ", 1)
        return f"{address}, {city}"
    return place


def _geocode_tomtom(query):
    """Repli quand la BAN ne trouve rien : la recherche TomTom connaît les
    lieux (aéroports, gares, points d'intérêt) et pas seulement les
    adresses postales."""
    if not TOMTOM_API_KEY:
        return None
    url = TOMTOM_SEARCH_URL.format(query=urllib.parse.quote(query)) + "?" + urllib.parse.urlencode(
        {"key": TOMTOM_API_KEY, "limit": 1, "countrySet": "FR"}
    )
    results = _get_json(url).get("results") or []
    if not results:
        return None
    pos = results[0]["position"]
    return pos["lat"], pos["lon"]


# En dessous de ce score, la BAN n'a pas vraiment reconnu l'adresse — elle
# renvoie quand même son moins mauvais résultat, parfois à l'autre bout du
# pays.
BAN_SCORE_MIN = 0.6


def _ban_search(query, **extra):
    """Résultats de la BAN, du meilleur au moins bon : point, score, commune
    et nature du lieu (housenumber, street, municipality…)."""
    params = {"q": query, "limit": 5}
    params.update(extra)
    found = []
    for feature in _get_json(BAN_URL + "?" + urllib.parse.urlencode(params)).get("features") or []:
        lon, lat = feature["geometry"]["coordinates"]
        props = feature["properties"]
        found.append({
            "point": (lat, lon),
            "score": props.get("score") or 0.0,
            "city": props.get("city") or props.get("name") or "",
            "kind": props.get("type") or "",
        })
    return found


def _tomtom_place(query):
    """Recherche TomTom, sans faire échouer l'appelant si elle est
    indisponible (pas de clé, service injoignable) : None dans ce cas."""
    try:
        return _geocode_tomtom(query)
    except RoutingError:
        return None


def geocode(query):
    """Libellé de trajet d'un OM (« VILLE, adresse ») -> (lat, lon). Lève
    RoutingError si ni la BAN ni TomTom ne reconnaissent le lieu."""
    place = normalize_place(query)
    if not place:
        raise RoutingError("adresse vide")
    found = _ban_search(place, limit=1)
    if found:
        return found[0]["point"]
    fallback = _geocode_tomtom(place)
    if fallback:
        return fallback
    raise RoutingError(f"lieu introuvable : « {place} »")


# --------------------- adresse saisie à la main (écran Plan de Ramassage)
# La BAN répond toujours quelque chose, même quand elle n'a pas compris, et
# son classement peut surprendre : « Bonneval » lui vaut une rue de La
# Teste-de-Buch (Gironde) avant la commune de Bonneval (28), et « 3 rue des
# Fontaines, Luce » une rue de Lucy (76). Sur une tournée, un arrêt géocodé
# à 400 km fausse tout l'ordre de passage — d'où les garde-fous ci-dessous.
MINOR_WORDS = {"de", "du", "des", "la", "le", "les", "l", "d", "et", "a", "au", "aux"}
ABBREVIATIONS = {"st": "saint", "ste": "sainte", "sts": "saints", "stes": "saintes"}


def _name_key(text):
    """Les mots qui comptent pour comparer deux noms de lieu : sans accents
    ni ponctuation, sans code postal ni petits mots, « ST » valant
    « SAINT ». Même principe que la vérification des adresses lues sur un
    plan de ramassage (static/js/stops_ocr.js)."""
    words = re.split(r"[\s'’,-]+", _fold(re.sub(r"\d+", " ", text or "")))
    keys = [ABBREVIATIONS.get(w, w) for w in (re.sub(r"[^a-z]", "", word) for word in words)]
    return " ".join(k for k in keys if k and k not in MINOR_WORDS)


def _requested_city(address):
    """Commune visée par une adresse saisie : ce qui suit la dernière virgule
    (« 3 rue des Fontaines, Lucé »), ou ce qui suit le code postal
    (« Place des Épars 28000 Chartres »). Vide si l'adresse n'en nomme
    aucune — il n'y a alors rien à vérifier."""
    if "," in address:
        return address.rsplit(",", 1)[1].strip()
    match = re.search(r"\b\d{5}\b\s*(.+)$", address)
    return match.group(1).strip() if match else ""


def geocode_address(query):
    """Adresse en ordre naturel (« 12 rue X, Chartres ») -> (lat, lon).

    Les adresses de l'écran Plan de Ramassage viennent de l'autocomplétion
    BAN), donc déjà dans le bon ordre : leur appliquer le ré-ordonnancement
    de normalize_place() les casserait. Seul « Dépôt KENT » reste traduit en
    adresse de l'entreprise. On retient, dans l'ordre :

    1. la commune exactement nommée, si c'est tout ce que l'adresse dit ;
    2. le meilleur résultat situé dans la commune demandée — ou, si
       l'adresse n'en nomme aucune, le meilleur résultat s'il est sûr ;
    3. l'avis de la recherche TomTom, qui connaît les lieux que la BAN
       ignore (gares, mairies, aéroports) ;
    4. à défaut, la commune demandée : le bon village vaut mieux qu'une rue
       homonyme à l'autre bout du pays ;
    5. faute de mieux, le premier résultat de la BAN.
    """
    place = (query or "").strip()
    if is_depot(place):
        place = normalize_place(place)
    if not place:
        raise RoutingError("adresse vide")

    found = _ban_search(place)
    wanted = _name_key(place)
    for match in found:
        if match["kind"] == "municipality" and _name_key(match["city"]) == wanted:
            return match["point"]

    city = _requested_city(place)
    if city:
        for match in found:
            if _name_key(match["city"]) == _name_key(city):
                return match["point"]
    elif found and found[0]["score"] >= BAN_SCORE_MIN:
        return found[0]["point"]

    fallback = _tomtom_place(place)
    if fallback:
        return fallback
    if city:
        towns = _ban_search(city, type="municipality", limit=1)
        if towns:
            return towns[0]["point"]
    if found:
        return found[0]["point"]
    raise RoutingError(f"lieu introuvable : « {place} »")


def _datetime_param(mission_date, time):
    """« 2026-09-20 » + « 08:00 » -> « 2026-09-20T08:00:00 ». Renvoie None
    si la date est incomplète ou déjà passée : TomTom refuse une heure
    dans le passé, on retombe alors sur le trafic courant."""
    if not mission_date or not time:
        return None
    try:
        dt = datetime.fromisoformat(f"{mission_date}T{time.replace('h', ':')}")
    except ValueError:
        return None
    return None if dt <= datetime.now() else dt.strftime("%Y-%m-%dT%H:%M:%S")


def estimate_route(origin, destination, mission_date=None, start_time=None, end_time=None):
    """Renvoie {duration_s, distance_m, traffic_delay_s, departure}.

    Trafic calculé pour un départ à `start_time` en priorité, sinon pour
    une arrivée à `end_time` (`departure` vaut alors cette heure d'arrivée)."""
    if not TOMTOM_API_KEY:
        raise RoutingError(
            "Clé TomTom absente : renseignez TOMTOM_API_KEY pour activer l'estimation."
        )
    (lat1, lon1), (lat2, lon2) = geocode(origin), geocode(destination)

    params = {"key": TOMTOM_API_KEY, "travelMode": "car", "traffic": "true"}
    if start_time:
        departure = _datetime_param(mission_date, start_time)
        if departure:
            params["departAt"] = departure
    else:
        departure = _datetime_param(mission_date, end_time)
        if departure:
            params["arriveAt"] = departure

    url = TOMTOM_ROUTE_URL.format(coords=f"{lat1},{lon1}:{lat2},{lon2}")
    data = _get_json(url + "?" + urllib.parse.urlencode(params))
    routes = data.get("routes") or []
    if not routes:
        raise RoutingError("aucun itinéraire trouvé entre ces deux points")
    summary = routes[0]["summary"]
    return {
        "duration_s": summary.get("travelTimeInSeconds", 0),
        "distance_m": summary.get("lengthInMeters", 0),
        "traffic_delay_s": summary.get("trafficDelayInSeconds", 0),
        "departure": departure,
    }


def format_duration(seconds):
    """3900 -> « 1 h 05 », 900 -> « 15 min »."""
    minutes = int(round(seconds / 60))
    h, m = divmod(minutes, 60)
    return f"{h} h {m:02d}" if h else f"{m} min"


def add_minutes(start_time, seconds):
    """« 08:00 » + 3900 s -> « 09:05 » (secondes négatives : on recule).
    None si l'heure est vide ou illisible."""
    try:
        base = datetime.strptime((start_time or "").replace("h", ":"), "%H:%M")
    except ValueError:
        return None
    total = base.hour * 60 + base.minute + int(round(seconds / 60))
    return f"{(total // 60) % 24:02d}:{total % 60:02d}"


# ------------------------------------------------ itinéraire chauffeur
# Lien Google Maps (navigation turn-by-turn) joint à l'email d'envoi de
# l'OM, si le chauffeur a coché « Envoyer l'itinéraire » sur sa fiche.
ARROW = " → "


def _driving_places(legs):
    """Lieux traversés par les trajets de conduite réels d'une mission
    (véhicule affecté, hors points de contrôle et relais — donc hors
    pauses, qui n'ont pas de véhicule), dans l'ordre des lignes. Un trajet
    « A → B » ajoute A (si différent du dernier lieu déjà ajouté) puis B."""
    places = []
    for leg in legs or []:
        if leg.get("is_relay") or leg.get("is_checkpoint") or not leg.get("vehicle_id"):
            continue
        label = leg.get("label") or ""
        if ARROW not in label:
            continue
        origin, _, destination = label.partition(ARROW)
        origin, destination = origin.strip(), destination.strip()
        if not origin or not destination:
            continue
        if not places or places[-1].lower() != origin.lower():
            places.append(origin)
        places.append(destination)
    return places


def build_driver_itinerary_url(legs):
    """Lien https://www.google.com/maps/dir/... pour l'itinéraire complet
    d'une mission (arrêts intermédiaires en waypoints), pensé pour être
    ouvert depuis un téléphone :
    - le dépôt de départ est omis de l'URL -> Google Maps utilise la
      position actuelle du chauffeur comme origine ;
    - le dépôt d'arrivée (et tout dépôt traversé en cours de route) est
      remplacé par l'adresse réelle de l'entreprise, comme pour le
      géocodage (voir normalize_place).
    None si la mission n'a pas au moins 2 lieux de conduite exploitables."""
    places = _driving_places(legs)
    if len(places) < 2:
        return None

    origin = None if is_depot(places[0]) else normalize_place(places[0])
    rest = [normalize_place(p) for p in places[1:]]

    params = {"api": "1", "travelmode": "driving", "destination": rest[-1]}
    if origin:
        params["origin"] = origin
    waypoints = rest[:-1]
    if waypoints:
        params["waypoints"] = "|".join(waypoints)
    return "https://www.google.com/maps/dir/?" + urllib.parse.urlencode(params, safe="|")


# ------------------------------------------- tournée : ordre le plus court
# Écran Plan de Ramassage : remettre une liste d'adresses dans l'ordre qui raccourcit
# le trajet. Rien n'est imposé — ni le premier arrêt, ni le dernier : le seul
# critère est la longueur totale. C'est le repli de l'optimisation Google Maps
# du navigateur : il ne coûte aucun appel de plus que le géocodage (donc
# aucune clé) et raisonne à vol d'oiseau, ce qui suffit à trouver le bon
# enchaînement d'une tournée de ramassage. Les kilomètres réels, eux, viennent
# de Google quand son itinéraire routier est disponible.
EARTH_RADIUS_KM = 6371.0

# Nombre d'ordres de départ affinés par la recherche locale. Celle-ci ne sort
# pas d'un minimum local : repartir de plusieurs ordres différents (les
# meilleurs du plus proche voisin) et garder le meilleur résultat vaut bien
# mieux qu'un seul essai, pour un temps de calcul qui reste négligeable.
IMPROVED_STARTS = 5


def haversine_km(a, b):
    """Distance à vol d'oiseau entre deux points (lat, lon), en km."""
    lat1, lon1, lat2, lon2 = radians(a[0]), radians(a[1]), radians(b[0]), radians(b[1])
    h = sin((lat2 - lat1) / 2) ** 2 + cos(lat1) * cos(lat2) * sin((lon2 - lon1) / 2) ** 2
    return 2 * EARTH_RADIUS_KM * asin(sqrt(h))


def tour_legs_km(points):
    """Longueur de chaque étape, pour des points déjà dans l'ordre de passage."""
    return [haversine_km(points[i], points[i + 1]) for i in range(len(points) - 1)]


def _nearest_neighbour(dist, n, start):
    """Un premier ordre : depuis `start`, on saute chaque fois au point non
    encore visité le plus proche."""
    free = [i for i in range(n) if i != start]
    order = [start]
    while free:
        nearest = min(free, key=lambda i: dist[order[-1]][i])
        free.remove(nearest)
        order.append(nearest)
    return order


def _variants(order):
    """Tous les remaniements d'un ordre de passage, un par un. Deux familles,
    complémentaires : renverser un tronçon (2-opt, qui défait les croisements)
    et déplacer un groupe de 1 à 3 arrêts ailleurs, dans un sens ou dans
    l'autre (Or-opt, qui déplace une grappe d'arrêts voisins)."""
    last = len(order) - 1
    for i in range(0, last + 1):
        for j in range(i + 1, last + 1):
            yield order[:i] + order[i:j + 1][::-1] + order[j + 1:]
    for size in (1, 2, 3):
        for i in range(0, last - size + 2):
            segment, rest = order[i:i + size], order[:i] + order[i + size:]
            for pos in range(0, len(rest) + 1):
                yield rest[:pos] + segment + rest[pos:]
                if size > 1:
                    yield rest[:pos] + segment[::-1] + rest[pos:]


def _improve(order, length):
    """Recherche locale : on garde tout remaniement qui raccourcit le trajet,
    et on recommence tant qu'il y a à gagner. Renvoie (ordre, longueur)."""
    best = length(order)
    improved = True
    while improved:
        improved = False
        # Les remaniements d'une passe sont ceux de l'ordre du début de passe
        # (le générateur en garde une copie) : chacun reste une permutation
        # complète, et n'est retenu que s'il bat le meilleur en cours.
        for candidate in _variants(order):
            value = length(candidate)
            if value < best - 1e-9:
                order, best, improved = candidate, value, True
    return order, best


def shortest_tour_order(points):
    """Indices de `points` réordonnés pour que le trajet soit le plus court.

    Aucun arrêt n'est imposé à un bout ou à l'autre : le calcul choisit aussi
    par où commencer et par où finir. Deux temps — un premier ordre grossier
    (plus proche voisin, essayé depuis chaque arrêt possible, plus l'ordre de
    saisie), puis une recherche locale qui le raccourcit (voir _improve). Sur
    une tournée (quelques dizaines d'arrêts) le résultat est l'optimum ou tout
    près, pour un temps de calcul négligeable — là où une résolution exacte
    exploserait.
    """
    n = len(points)
    if n < 3:
        return list(range(n))

    dist = [[haversine_km(a, b) for b in points] for a in points]

    def length(seq):
        return sum(dist[seq[i]][seq[i + 1]] for i in range(len(seq) - 1))

    candidates = [_nearest_neighbour(dist, n, start) for start in range(n)]
    candidates.append(list(range(n)))
    candidates.sort(key=length)
    results = [_improve(c, length) for c in candidates[:IMPROVED_STARTS]]
    return min(results, key=lambda r: r[1])[0]
