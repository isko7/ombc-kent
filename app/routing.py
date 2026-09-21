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
import urllib.parse
import urllib.request
from datetime import datetime

from app.config import COMPANY, TOMTOM_API_KEY
from app.utils import is_depot

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


def geocode(query):
    """Adresse libre -> (lat, lon). Lève RoutingError si rien ne matche."""
    query = normalize_place(query)
    if not query:
        raise RoutingError("adresse vide")
    url = BAN_URL + "?" + urllib.parse.urlencode({"q": query, "limit": 1})
    features = _get_json(url).get("features") or []
    if features:
        lon, lat = features[0]["geometry"]["coordinates"]
        return lat, lon
    fallback = _geocode_tomtom(query)
    if fallback:
        return fallback
    raise RoutingError(f"lieu introuvable : « {query} »")


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
