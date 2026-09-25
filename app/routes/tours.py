"""
Écran Plan de Ramassage : une liste d'adresses, remise dans l'ordre qui raccourcit le
trajet, et la carte de l'itinéraire — indépendant des ordres de mission.

Rien n'est imposé : le calcul choisit aussi le premier et le dernier arrêt.
C'est pour cela qu'il commence ici et non dans le navigateur — un itinéraire
Google Maps veut un départ et une arrivée connus. Cette vue géocode donc les
adresses (Base Adresse Nationale, puis recherche TomTom) et les ordonne à vol
d'oiseau (`app/routing.py`) ; le navigateur demande ensuite à Google, s'il est
disponible, de réoptimiser le milieu du parcours sur les distances routières
réelles et d'en tracer la carte (voir `static/js/tours.js`).

Appelée avec `optimize=0`, elle ne réordonne rien : elle renvoie les
coordonnées et les distances de l'ordre reçu, pour redessiner la carte après
un glisser-déposer quand l'itinéraire routier de Google n'est pas disponible.
"""
from concurrent.futures import ThreadPoolExecutor

from flask import Blueprint, jsonify, render_template, request

from app import routing
from app.config import COMPANY, GOOGLE_MAPS_API_KEY
from app.routes.settings import get_address_search_provider

bp = Blueprint("tours", __name__, url_prefix="/tournees")

# Plafond côté serveur : le solveur reste sous la seconde jusqu'à une
# quarantaine d'arrêts.
MAX_STOPS = 40

# Plafond de l'écran, plus bas : au-delà, Google Maps refuse l'itinéraire
# (25 points de passage au maximum). Repris par le gabarit et par tours.js.
BROWSER_MAX_STOPS = 25

# Géocodages menés de front : un aller-retour vers la BAN prend ~200 ms, les
# enchaîner rendrait une tournée de 25 arrêts inutilement longue à calculer.
GEOCODE_WORKERS = 8


@bp.route("/")
def planner_view():
    return render_template(
        "tours/planner.html",
        google_maps_api_key=GOOGLE_MAPS_API_KEY,
        address_search_provider=get_address_search_provider(),
        depot_address=f"{COMPANY['address']}, {COMPANY['postal_code']} {COMPANY['city']}",
        max_stops=BROWSER_MAX_STOPS,
    )


def _geocode(address):
    """(lat, lon) ou (None, message) — l'erreur est renvoyée plutôt que levée
    pour pouvoir dire *quelle* adresse n'a pas été reconnue."""
    try:
        return routing.geocode_address(address), None
    except routing.RoutingError as e:
        return None, str(e)


@bp.route("/optimiser", methods=["POST"])
def optimize_tour():
    """Appelé en fetch depuis l'écran : `address` (répété) et `optimize`
    (« 0 » pour garder l'ordre reçu). Réponse en JSON.

    `order` est la liste des indices des adresses reçues, dans l'ordre de
    passage ; `points` suit l'ordre de la demande (le navigateur les garde en
    cache par adresse). Les distances sont à vol d'oiseau : elles servent à
    trancher entre deux ordres, pas à annoncer un kilométrage."""
    addresses = [a.strip() for a in request.form.getlist("address")]
    optimize = request.form.get("optimize") != "0"

    if len(addresses) < 2:
        return jsonify({"ok": False, "error": "Il faut au moins deux adresses."}), 400
    if len(addresses) > MAX_STOPS:
        return jsonify({"ok": False, "error": f"{MAX_STOPS} adresses au maximum."}), 400
    if not all(addresses):
        return jsonify({"ok": False, "error": "Une des adresses est vide."}), 400

    with ThreadPoolExecutor(max_workers=GEOCODE_WORKERS) as pool:
        geocoded = list(pool.map(_geocode, addresses))
    for index, (point, error) in enumerate(geocoded):
        if error:
            return jsonify({
                "ok": False,
                "failed_index": index,
                "error": f"Adresse introuvable : « {addresses[index]} » ({error}).",
            }), 400

    points = [point for point, _ in geocoded]
    order = (routing.shortest_tour_order(points) if optimize
             else list(range(len(points))))
    legs = routing.tour_legs_km([points[i] for i in order])
    return jsonify({
        "ok": True,
        "order": order,
        "points": [{"lat": lat, "lng": lon} for lat, lon in points],
        "legs_km": [round(km, 2) for km in legs],
        "total_km": round(sum(legs), 2),
    })
