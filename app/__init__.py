from flask import Flask, redirect, url_for

from app.config import SECRET_KEY, MAX_UPLOAD_MB
from app.db import init_db
from app.utils import register_jinja_filters


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

    try:
        init_db()
    except Exception as e:  # pragma: no cover - visible dans les logs Vercel
        app.logger.warning("init_db a échoué au démarrage : %s", e)
    register_jinja_filters(app)

    from app.routes.drivers import bp as drivers_bp
    from app.routes.vehicles import bp as vehicles_bp
    from app.routes.clients import bp as clients_bp
    from app.routes.missions import bp as missions_bp
    from app.routes.templates_admin import bp as templates_bp
    from app.routes.admin import bp as admin_bp

    app.register_blueprint(drivers_bp)
    app.register_blueprint(vehicles_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(missions_bp)
    app.register_blueprint(templates_bp)
    app.register_blueprint(admin_bp)

    @app.route("/")
    def index():
        return redirect(url_for("missions.list_missions_view"))

    @app.route("/healthz")
    def healthz():
        return {"ok": True}

    @app.errorhandler(404)
    def not_found(e):
        return "Page introuvable", 404

    return app
