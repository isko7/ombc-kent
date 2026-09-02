"""
Configuration de l'application.

Toutes les valeurs peuvent être surchargées par des variables
d'environnement (ou un fichier .env à la racine du projet — voir
.env.example). Aucune dépendance externe requise : le petit loader
ci-dessous lit .env s'il existe, sans écraser des variables déjà
définies dans l'environnement réel (donc les variables Vercel gagnent).
"""
import os
from pathlib import Path
from urllib.parse import urlparse, unquote

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
DEBUG = env("FLASK_DEBUG", "0") == "1"

# Taille max d'une pièce jointe uploadée. Attention : au-delà de la valeur
# de `max_allowed_packet` de votre serveur MySQL (souvent 4 à 16 Mo sur les
# offres managées), l'insertion du LONGBLOB échouera.
MAX_UPLOAD_MB = int(env("MAX_UPLOAD_MB", "8"))


# --- Base de données (MySQL) -----------------------------------------
# Fournir soit DATABASE_URL (mysql://user:pass@host:port/dbname), soit les
# variables MYSQL_* individuelles. SSL activé par défaut (obligatoire chez
# la plupart des hébergeurs MySQL managés) ; MYSQL_SSL=0 pour le désactiver
# en local.
def _db_config():
    url = env("DATABASE_URL") or env("MYSQL_URL")
    if url:
        p = urlparse(url)
        cfg = {
            "host": p.hostname or "localhost",
            "port": p.port or 3306,
            "user": unquote(p.username) if p.username else "root",
            "password": unquote(p.password) if p.password else "",
            "database": (p.path or "/").lstrip("/") or "kent",
        }
        ssl_flag = env("MYSQL_SSL")
        if ssl_flag is None:
            # Par défaut : SSL sauf si l'hôte est local.
            cfg["ssl"] = cfg["host"] not in ("localhost", "127.0.0.1", "::1")
        else:
            cfg["ssl"] = ssl_flag not in ("0", "false", "no", "")
        return cfg
    return {
        "host": env("MYSQL_HOST", "localhost"),
        "port": int(env("MYSQL_PORT", "3306")),
        "user": env("MYSQL_USER", "root"),
        "password": env("MYSQL_PASSWORD", ""),
        "database": env("MYSQL_DATABASE", "kent"),
        "ssl": env("MYSQL_SSL", "0") not in ("0", "false", "no", ""),
    }


DB_CONFIG = _db_config()


# --- PDF -------------------------------------------------------------
# PDF_ENGINE = "wkhtmltopdf" -> binaire système local (dev)
# PDF_ENGINE = "http"        -> appelle la fonction serverless Node
#                               /api/render_pdf (Chrome headless) — Vercel
PDF_ENGINE = env("PDF_ENGINE", "wkhtmltopdf")
WKHTMLTOPDF_BIN = env("WKHTMLTOPDF_BIN", "wkhtmltopdf")
# Base URL du service de rendu HTTP. Si vide, on utilise VERCEL_URL (auto)
# puis http://localhost:3000 en dernier recours.
PDF_RENDER_URL = env("PDF_RENDER_URL", "")
PDF_RENDER_SECRET = env("PDF_RENDER_SECRET", "")


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


# --- Email -------------------------------------------------------------
# SMTP_AUTH_METHOD = "basic"       -> SMTP classique (host/port/user/pass)
# SMTP_AUTH_METHOD = "oauth2_o365" -> Microsoft 365 / Exchange Online (MSAL)
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
