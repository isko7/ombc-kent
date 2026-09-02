"""
Configuration de l'application.

Toutes les valeurs peuvent être surchargées par des variables
d'environnement (ou un fichier .env à la racine du projet — voir
.env.example). Aucune dépendance externe requise : le petit loader
ci-dessous lit .env s'il existe, sans écraser des variables déjà
définies dans l'environnement réel.
"""
import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent


def _load_dotenv(path: Path):
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


_load_dotenv(BASE_DIR / ".env")


def env(key, default=None):
    return os.environ.get(key, default)


# --- Général -----------------------------------------------------------
SECRET_KEY = env("SECRET_KEY", "dev-secret-change-me")
PORT = int(env("PORT", "8000"))
DEBUG = env("FLASK_DEBUG", "1") == "1"

# --- Stockage ------------------------------------------------------------
DATA_DIR = Path(env("DATA_DIR", str(BASE_DIR / "data")))
DB_PATH = str(DATA_DIR / "app.db")
UPLOADS_DIR = DATA_DIR / "uploads"
MAX_UPLOAD_MB = int(env("MAX_UPLOAD_MB", "20"))

# --- Coordonnées de l'entreprise (affichées sur l'OM et le BC) ---------
COMPANY = {
    "name": env("COMPANY_NAME", "Transports KENT"),
    "address": env("COMPANY_ADDRESS", "14 Rue du Fer à Cheval"),
    "postal_code": env("COMPANY_POSTAL_CODE", "28200"),
    "city": env("COMPANY_CITY", "ST-DENIS-LANNERAY"),
    "phone": env("COMPANY_PHONE", "07 44 90 60 38"),
    "siret": env("COMPANY_SIRET", "93073109600010"),
}
OM_LEGAL_REF = env("OM_LEGAL_REF", "28/11/2011 Art1-1er-2")
BC_LEGAL_REF = env("BC_LEGAL_REF", "28/12/2011")

# --- PDF -------------------------------------------------------------
# Moteur HTML -> PDF. "wkhtmltopdf" appelle le binaire système du même nom
# (le plus simple à installer partout : apt/choco/brew, ou binaire portable).
# Le code est isolé dans pdf_service.render_html_to_pdf() : remplacer par
# WeasyPrint ou un navigateur headless (Playwright/Puppeteer) ne touche
# qu'une seule fonction.
WKHTMLTOPDF_BIN = env("WKHTMLTOPDF_BIN", "wkhtmltopdf")

# --- Email -------------------------------------------------------------
# SMTP_AUTH_METHOD = "basic"      -> SMTP classique (host/port/user/pass)
#                                    fonctionne avec Gmail (mot de passe
#                                    d'application), OVH, Infomaniak, etc.
# SMTP_AUTH_METHOD = "oauth2_o365" -> Microsoft 365 / Exchange Online via
#                                    OAuth2 (client credentials + MSAL),
#                                    nécessaire car O365 a désactivé
#                                    l'authentification SMTP basique.
SMTP_AUTH_METHOD = env("SMTP_AUTH_METHOD", "basic")

SMTP_HOST = env("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(env("SMTP_PORT", "587"))
SMTP_USER = env("SMTP_USER", "")
SMTP_PASS = env("SMTP_PASS", "")
SMTP_FROM_NAME = env("SMTP_FROM_NAME", COMPANY["name"])
SMTP_FROM_EMAIL = env("SMTP_FROM_EMAIL", SMTP_USER)

# Pour SMTP_AUTH_METHOD=oauth2_o365 :
O365_TENANT_ID = env("O365_TENANT_ID", "")
O365_CLIENT_ID = env("O365_CLIENT_ID", "")
O365_CLIENT_SECRET = env("O365_CLIENT_SECRET", "")
O365_SENDER_EMAIL = env("O365_SENDER_EMAIL", SMTP_USER)
