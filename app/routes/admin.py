"""
Route d'administration protégée par un secret (env SEED_SECRET).

Sert à initialiser la base après le premier déploiement Vercel, sans avoir
besoin d'ouvrir un accès MySQL depuis votre poste :

    GET /admin/init?key=<SEED_SECRET>          -> schéma + templates
    GET /admin/init?key=<SEED_SECRET>&demo=1   -> + données de démo

Si SEED_SECRET n'est pas défini, la route répond 404.
"""
from flask import Blueprint, request, jsonify, abort

from app.config import env
from app.db import init_db
from app.seeding import seed_templates, seed_demo_data

bp = Blueprint("admin", __name__, url_prefix="/admin")


@bp.route("/init")
def init():
    secret = env("SEED_SECRET")
    if not secret:
        abort(404)
    if request.args.get("key") != secret:
        abort(403)

    actions = []
    init_db(force=True)
    actions.append("schéma vérifié/créé")
    actions += seed_templates()
    if request.args.get("demo") in ("1", "true", "yes"):
        demo = seed_demo_data()
        actions += demo or ["données de démo déjà présentes"]

    return jsonify({"ok": True, "actions": actions})
