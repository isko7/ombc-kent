"""
Route d'administration protégée par un secret (env SEED_SECRET).

Sert à initialiser la base après le premier déploiement Vercel, sans avoir
besoin d'ouvrir un accès MySQL depuis votre poste :

    GET /admin/init?key=<SEED_SECRET>          -> schéma + templates
    GET /admin/init?key=<SEED_SECRET>&demo=1   -> + données de démo

Si SEED_SECRET n'est pas défini, la route répond 404.
"""
import time
import traceback

from flask import Blueprint, request, jsonify, abort

from app.config import env
from app.db import init_db, check_connection
from app.seeding import seed_templates, seed_demo_data

bp = Blueprint("admin", __name__, url_prefix="/admin")


def _require_secret():
    secret = env("SEED_SECRET")
    if not secret:
        abort(404)
    if request.args.get("key") != secret:
        abort(403)


@bp.route("/dbcheck")
def dbcheck():
    """Diagnostic connexion MySQL : /admin/dbcheck?key=<SEED_SECRET>"""
    _require_secret()
    result = check_connection()
    return jsonify(result), (200 if result.get("ok") else 500)


@bp.route("/init")
def init():
    _require_secret()

    steps = {}
    try:
        t0 = time.monotonic()
        steps["schema"] = init_db(force=True, report=True)
        steps["schema_ms"] = round((time.monotonic() - t0) * 1000)

        t0 = time.monotonic()
        steps["templates"] = seed_templates()
        steps["templates_ms"] = round((time.monotonic() - t0) * 1000)

        if request.args.get("demo") in ("1", "true", "yes"):
            t0 = time.monotonic()
            steps["demo"] = seed_demo_data() or ["déjà présent"]
            steps["demo_ms"] = round((time.monotonic() - t0) * 1000)
    except Exception as e:
        steps["ok"] = False
        steps["error"] = f"{type(e).__name__}: {e}"
        steps["trace"] = traceback.format_exc().splitlines()[-6:]
        return jsonify(steps), 500

    steps["ok"] = True
    return jsonify(steps)
