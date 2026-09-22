"""
Authentification : jeton JWT (HS256) transporté par un cookie HttpOnly.

Modèle volontairement minimal — les seuls comptes sont des fiches
chauffeur. Un chauffeur peut se connecter si sa fiche a « Accès à
l'application » coché, un identifiant et un mot de passe (écran
Chauffeurs).

Deux niveaux de droits, portés par la même fiche :

* **chauffeur** : ne voit que le Planning et les Ordres de mission, et
  uniquement *les siens* (voir DRIVER_ENDPOINTS). Les écrans Chauffeurs /
  Véhicules / Clients / Templates lui sont fermés et masqués du menu.
* **administrateur** (`is_admin`) : accès complet, y compris la gestion
  des accès et la réinitialisation des mots de passe.

Un mot de passe réinitialisé par un administrateur vaut l'identifiant et
lève `must_change_password` : le chauffeur est alors bloqué sur l'écran
« changer mon mot de passe » tant qu'il n'en a pas choisi un autre.

Le jeton est *vérifié en base à chaque requête* (`load_current_user`) :
retirer l'accès à un chauffeur, le désactiver ou changer son mot de passe
le déconnecte immédiatement, sans attendre l'expiration du JWT. Le claim
`stamp` (empreinte du hash du mot de passe) assure ce dernier point.
"""
import hashlib
from datetime import datetime, timedelta, timezone
from functools import wraps

import jwt
from flask import abort, g, redirect, request, url_for
from werkzeug.security import check_password_hash, generate_password_hash

from app import repo
from app.config import AUTH_COOKIE_NAME, JWT_SECRET, JWT_TTL_HOURS

JWT_ALGORITHM = "HS256"

# pbkdf2:sha256 plutôt que le scrypt par défaut de Werkzeug : disponible
# partout (scrypt dépend de l'OpenSSL du runtime), et ~400 ms par
# vérification, ce qui reste confortable pour une page de connexion.
PASSWORD_HASH_METHOD = "pbkdf2:sha256"

# Points d'entrée accessibles sans être connecté. `admin.*` et
# `planning.calendar_feed` sont exclus parce qu'ils portent déjà leur
# propre secret (SEED_SECRET / CALENDAR_FEED_TOKEN) et sont appelés par
# des clients qui ne peuvent pas passer par le formulaire de connexion
# (navigateur sans session, application Calendrier du téléphone).
PUBLIC_ENDPOINTS = {
    "auth.login",
    "auth.logout",
    "static",
    "healthz",
    "planning.calendar_feed",
}
PUBLIC_BLUEPRINTS = {"admin"}

# Points d'entrée accessibles à un chauffeur SANS droits d'administration.
# C'est une liste blanche : tout écran ajouté plus tard est donc réservé
# aux administrateurs par défaut, plutôt qu'exposé par oubli.
# Les vues qui portent sur une mission précise vérifient en plus que
# celle-ci lui appartient (missions._require_mission_access).
DRIVER_ENDPOINTS = {
    "index",
    "planning.calendar_view",
    "missions.list_missions_view",
    "missions.detail_mission",
    "missions.mission_pdf",
    "auth.change_password",
    "auth.save_personal_notes",
    "auth.logout",
}

# Seuls écrans atteignables tant qu'un mot de passe doit être renouvelé.
PASSWORD_CHANGE_ENDPOINTS = {"auth.change_password", "auth.logout", "static", "healthz"}

# Écritures qu'un chauffeur peut faire malgré la lecture seule : elles ne
# portent que sur son propre compte, pas sur les données de l'application.
SELF_SERVICE_ENDPOINTS = {"auth.change_password", "auth.save_personal_notes", "auth.logout"}


# ------------------------------------------------------------- mots de passe
def hash_password(password):
    return generate_password_hash(password, method=PASSWORD_HASH_METHOD)


def verify_password(driver, password):
    stored = (driver or {}).get("password_hash")
    if not stored or not password:
        return False
    return check_password_hash(stored, password)


def _password_stamp(password_hash):
    """Empreinte courte du hash, embarquée dans le jeton. Un changement de
    mot de passe change l'empreinte, donc invalide les jetons émis avant."""
    digest = hashlib.sha256((password_hash or "").encode("utf-8")).hexdigest()
    return digest[:16]


# --------------------------------------------------------------------- JWT
def issue_token(driver):
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(driver["id"]),
        "usr": driver.get("username") or "",
        "name": f"{driver['first_name']} {driver['last_name']}",
        "stamp": _password_stamp(driver.get("password_hash")),
        "iat": now,
        "exp": now + timedelta(hours=JWT_TTL_HOURS),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)


def decode_token(token):
    """Renvoie le payload, ou None si le jeton est absent, expiré ou
    signé avec un autre secret."""
    if not token:
        return None
    try:
        return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except jwt.PyJWTError:
        return None


LOCAL_HOSTS = ("localhost", "127.0.0.1", "[::1]", "::1")


def _cookie_is_secure():
    """Secure partout, sauf sur un serveur de développement local.

    Le critère est l'hôte, pas FLASK_DEBUG : en http:// un cookie Secure
    n'est jamais renvoyé par le navigateur (la connexion boucle sur la page
    de login), et à l'inverse un FLASK_DEBUG oublié à 1 en production ne
    doit pas désactiver le drapeau."""
    host = (request.host or "").split(":")[0]
    return host not in LOCAL_HOSTS


def set_auth_cookie(response, token):
    response.set_cookie(
        AUTH_COOKIE_NAME, token,
        max_age=JWT_TTL_HOURS * 3600,
        httponly=True,
        secure=_cookie_is_secure(),
        samesite="Lax",
        path="/",
    )
    return response


def clear_auth_cookie(response):
    response.delete_cookie(AUTH_COOKIE_NAME, path="/")
    return response


# ----------------------------------------------------- utilisateur courant
def load_current_user():
    """Chauffeur connecté, ou None. Le jeton ne fait qu'identifier la fiche :
    le droit d'accès est relu en base à chaque requête."""
    payload = decode_token(request.cookies.get(AUTH_COOKIE_NAME))
    if not payload:
        return None
    try:
        driver_id = int(payload.get("sub"))
    except (TypeError, ValueError):
        return None

    driver = repo.get_driver(driver_id)
    if not driver or not driver.get("can_login") or not driver.get("active"):
        return None
    if not driver.get("password_hash"):
        return None
    if payload.get("stamp") != _password_stamp(driver["password_hash"]):
        return None
    return driver


def current_user():
    return getattr(g, "current_user", None)


def is_admin():
    user = current_user()
    return bool(user and user.get("is_admin"))


def requires_admin_endpoint():
    """Vrai si le point d'entrée courant est réservé aux administrateurs."""
    return request.endpoint not in DRIVER_ENDPOINTS


def must_change_password():
    user = current_user()
    return bool(user and user.get("must_change_password"))


def is_public_request():
    endpoint = request.endpoint
    if endpoint is None:  # 404 : laissé au gestionnaire d'erreurs de Flask
        return True
    return endpoint in PUBLIC_ENDPOINTS or request.blueprint in PUBLIC_BLUEPRINTS


def wants_json():
    """Vrai si la requête vient d'un fetch/XHR plutôt que d'une navigation.
    Ces appels-là doivent recevoir un 401 JSON : suivre une redirection vers
    la page de connexion leur renverrait du HTML, et le `resp.json()` côté
    navigateur échouerait sur un message incompréhensible."""
    if request.headers.get("X-Requested-With") == "XMLHttpRequest":
        return True
    # En-tête envoyé par tous les navigateurs modernes : "document" pour une
    # navigation, "empty" pour un fetch().
    if request.headers.get("Sec-Fetch-Dest") == "empty":
        return True
    accept = request.headers.get("Accept", "")
    return "application/json" in accept and "text/html" not in accept


def admin_required(view):
    """Garde-fou explicite, en complément du contrôle central de
    app/__init__.py (qui refuse déjà tout ce qui n'est pas dans
    DRIVER_ENDPOINTS à un chauffeur non administrateur)."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if not is_admin():
            abort(403)
        return view(*args, **kwargs)
    return wrapper


def login_required(view):
    """Garde-fou explicite. L'application protège déjà toutes les routes
    via `before_request` (voir app/__init__.py) ; ce décorateur reste utile
    pour une route ajoutée hors de ce circuit."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        if current_user() is None:
            return redirect(url_for("auth.login", next=request.full_path))
        return view(*args, **kwargs)
    return wrapper
