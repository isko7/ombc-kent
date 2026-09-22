"""
Écran de connexion / déconnexion.

Les comptes sont les fiches chauffeur ayant « Accès à l'application »
(voir app/auth.py). Rien d'autre n'est exposé sans être connecté : le
garde-fou global vit dans app/__init__.py.
"""
from urllib.parse import urlparse

from flask import (Blueprint, flash, jsonify, make_response, redirect,
                   render_template, request, url_for)

from app import repo
from app.auth import (clear_auth_cookie, current_user, hash_password, issue_token,
                      set_auth_cookie, verify_password)

bp = Blueprint("auth", __name__)

MIN_PASSWORD_LENGTH = 8


def _safe_next(target):
    """N'accepte qu'une redirection interne : un `?next=` pointant vers un
    autre domaine renverrait l'utilisateur fraîchement connecté ailleurs."""
    if not target:
        return None
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/"):
        return None
    # « //evil.com » et « /\evil.com » sont lus comme des URL absolues par
    # les navigateurs, alors que urlparse ne voit qu'un chemin.
    if target[1:2] in ("/", "\\"):
        return None
    return target


@bp.route("/connexion", methods=["GET", "POST"])
def login():
    next_url = _safe_next(request.values.get("next"))

    if current_user():
        return redirect(next_url or url_for("planning.calendar_view"))

    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        driver = repo.get_driver_by_username(username)

        # Message unique quelle que soit la cause : ne pas révéler quels
        # identifiants existent.
        if not driver or not driver.get("can_login") or not driver.get("active") \
                or not verify_password(driver, password):
            flash("Identifiant ou mot de passe incorrect.", "error")
            return render_template("auth/login.html", username=username, next_url=next_url), 401

        # Mot de passe réinitialisé par un administrateur : on envoie
        # directement sur le renouvellement, le garde-fou global bloquerait
        # de toute façon tout le reste.
        target = (url_for("auth.change_password") if driver.get("must_change_password")
                  else (next_url or url_for("planning.calendar_view")))
        response = make_response(redirect(target))
        return set_auth_cookie(response, issue_token(driver))

    return render_template("auth/login.html", username="", next_url=next_url)


@bp.route("/changer-mot-de-passe", methods=["GET", "POST"])
def change_password():
    """Renouvellement du mot de passe par l'utilisateur lui-même.

    Obligatoire après une réinitialisation par un administrateur (le
    garde-fou global n'autorise plus que cet écran), et disponible à tout
    moment depuis son nom dans la barre du haut.
    """
    user = current_user()
    if not user:
        return redirect(url_for("auth.login"))

    forced = bool(user.get("must_change_password"))

    if request.method == "POST":
        current = request.form.get("current_password", "")
        new = request.form.get("new_password", "")
        confirm = request.form.get("new_password_confirm", "")

        errors = []
        # Après une réinitialisation, le mot de passe actuel est
        # l'identifiant : le redemander n'apporterait rien.
        if not forced and not verify_password(user, current):
            errors.append("Mot de passe actuel incorrect.")
        if len(new) < MIN_PASSWORD_LENGTH:
            errors.append(f"Le nouveau mot de passe doit faire au moins "
                          f"{MIN_PASSWORD_LENGTH} caractères.")
        elif new != confirm:
            errors.append("Les deux mots de passe saisis ne correspondent pas.")
        elif new == user.get("username"):
            errors.append("Choisissez un mot de passe différent de votre identifiant.")

        if errors:
            for message in errors:
                flash(message, "error")
            return render_template("auth/change_password.html", forced=forced), 400

        repo.set_password(user["id"], hash_password(new), must_change=False)
        flash("Mot de passe mis à jour.", "success")

        # Le jeton porte une empreinte du mot de passe : sans réémission,
        # l'utilisateur serait déconnecté par son propre changement.
        refreshed = repo.get_driver(user["id"])
        response = make_response(redirect(url_for("planning.calendar_view")))
        return set_auth_cookie(response, issue_token(refreshed))

    return render_template("auth/change_password.html", forced=forced)


@bp.route("/mes-notes", methods=["POST"])
def save_personal_notes():
    """Bloc-notes personnel de la barre du haut. Appelé en fetch depuis la
    fenêtre modale : chacun n'écrit que les siennes, y compris un chauffeur
    sans droits d'administration (c'est du self-service, au même titre que
    son mot de passe)."""
    user = current_user()
    if not user:
        return jsonify({"ok": False, "error": "Session expirée."}), 401
    notes = request.form.get("notes", "")
    repo.set_personal_notes(user["id"], notes.strip())
    return jsonify({"ok": True})


@bp.route("/deconnexion", methods=["GET", "POST"])
def logout():
    response = make_response(redirect(url_for("auth.login")))
    clear_auth_cookie(response)
    flash("Vous êtes déconnecté.", "success")
    return response
