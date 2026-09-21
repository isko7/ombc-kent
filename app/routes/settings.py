"""
Écran Réglages : réglages modifiables depuis l'interface (par opposition à
ceux figés en .env, comme les clés d'API). Pour l'instant, un seul réglage :
le fournisseur de recherche d'adresse du formulaire de mission.
"""
from flask import Blueprint, render_template, request, redirect, url_for, flash

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


@bp.route("/", methods=["GET", "POST"])
def settings_view():
    if request.method == "POST":
        provider = request.form.get("address_search_provider")
        if provider in ("google", "gouv"):
            repo.set_setting(ADDRESS_PROVIDER_KEY, provider)
            flash("Réglages enregistrés.", "success")
        return redirect(url_for("settings.settings_view"))

    saved_provider = repo.get_setting(ADDRESS_PROVIDER_KEY, ADDRESS_PROVIDER_DEFAULT)
    return render_template(
        "settings/form.html",
        address_search_provider=saved_provider,
        google_maps_configured=bool(GOOGLE_MAPS_API_KEY),
    )
