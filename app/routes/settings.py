"""
Réglage global : fournisseur de recherche d'adresse (Google Maps / Base
Adresse Nationale). Pas d'écran dédié : le dropdown vit directement dans le
formulaire Ordre de mission (juste au-dessus des Arrêts), sauvegardé en
AJAX. La table app_settings reste la source de vérité, lue via
get_address_search_provider().
"""
from flask import Blueprint, request, jsonify

from app import repo
from app.config import GOOGLE_MAPS_API_KEY

bp = Blueprint("settings", __name__, url_prefix="/reglages")

ADDRESS_PROVIDER_KEY = "address_search_provider"
ADDRESS_PROVIDER_DEFAULT = "google"


def get_address_search_provider():
    """"google" (Places, par défaut) ou "gouv" (Base Adresse Nationale). Se
    replie automatiquement sur "gouv" si GOOGLE_MAPS_API_KEY est absente,
    quel que soit le réglage enregistré."""
    value = repo.get_setting(ADDRESS_PROVIDER_KEY, ADDRESS_PROVIDER_DEFAULT)
    return value if GOOGLE_MAPS_API_KEY else "gouv"


@bp.route("/recherche-adresse", methods=["POST"])
def set_address_search_provider():
    """Appelé en fetch depuis le dropdown du formulaire de mission. Répond
    en JSON : le réglage est global, pas lié à une mission en particulier."""
    provider = request.form.get("address_search_provider")
    if provider not in ("google", "gouv"):
        return jsonify({"ok": False, "error": "Valeur invalide."}), 400
    repo.set_setting(ADDRESS_PROVIDER_KEY, provider)
    return jsonify({"ok": True, "address_search_provider": provider})
