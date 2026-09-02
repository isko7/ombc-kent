from flask import Flask, redirect, url_for

from app.config import SECRET_KEY, MAX_UPLOAD_MB, UPLOADS_DIR
from app.db import init_db
from app.utils import register_jinja_filters


def create_app():
    app = Flask(__name__)
    app.config["SECRET_KEY"] = SECRET_KEY
    app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_MB * 1024 * 1024

    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    init_db()
    register_jinja_filters(app)

    from app.routes.drivers import bp as drivers_bp
    from app.routes.vehicles import bp as vehicles_bp
    from app.routes.clients import bp as clients_bp
    from app.routes.missions import bp as missions_bp
    from app.routes.templates_admin import bp as templates_bp

    app.register_blueprint(drivers_bp)
    app.register_blueprint(vehicles_bp)
    app.register_blueprint(clients_bp)
    app.register_blueprint(missions_bp)
    app.register_blueprint(templates_bp)

    @app.route("/")
    def index():
        return redirect(url_for("missions.list_missions_view"))

    @app.errorhandler(404)
    def not_found(e):
        return "Page introuvable", 404

    return app
