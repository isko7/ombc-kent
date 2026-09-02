"""
Connexion SQLite + schéma de la base + petites fonctions utilitaires.

On utilise sqlite3 (bibliothèque standard de Python : aucune dépendance
à installer). Le fichier de base est stocké dans data/app.db.
Pour passer à PostgreSQL plus tard, voir la note dans le README :
le schéma SQL ci-dessous est volontairement écrit de façon portable
(types simples, pas de fonctions spécifiques à SQLite autres que
datetime('now') / AUTOINCREMENT) pour rendre la migration simple.
"""
import sqlite3
from pathlib import Path
from contextlib import contextmanager

from app.config import DB_PATH

SCHEMA = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS drivers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    last_name TEXT NOT NULL,
    first_name TEXT NOT NULL,
    email TEXT NOT NULL,
    phone TEXT,
    license_number TEXT,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS vehicles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT,
    plate TEXT NOT NULL UNIQUE,
    seats INTEGER,
    active INTEGER NOT NULL DEFAULT 1,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS clients (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    address TEXT,
    postal_code TEXT,
    city TEXT,
    phone TEXT,
    email TEXT,
    notes TEXT,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    type TEXT NOT NULL CHECK(type IN ('OM','BC')),
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 0,
    definition_html TEXT NOT NULL,
    version INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS missions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    reference TEXT UNIQUE,
    driver_id INTEGER NOT NULL REFERENCES drivers(id),
    mission_date TEXT NOT NULL,
    motif TEXT NOT NULL DEFAULT 'Transport Occasionnel',
    remarks TEXT,
    client_id INTEGER REFERENCES clients(id),
    emission_date TEXT,
    price TEXT,
    status TEXT NOT NULL DEFAULT 'brouillon',
    om_template_id INTEGER REFERENCES templates(id),
    bc_template_id INTEGER REFERENCES templates(id),
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS mission_legs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    vehicle_id INTEGER REFERENCES vehicles(id),
    label TEXT NOT NULL,
    is_checkpoint INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS mission_stops (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    position INTEGER NOT NULL,
    stop_type TEXT NOT NULL CHECK(stop_type IN ('prise_en_charge','depose')),
    stop_date TEXT NOT NULL,
    stop_time TEXT NOT NULL,
    address TEXT NOT NULL,
    city TEXT,
    passenger_count INTEGER NOT NULL DEFAULT 1,
    passenger_name TEXT,
    passenger_phone TEXT,
    booking_ref TEXT
);

CREATE TABLE IF NOT EXISTS attachments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    filename TEXT NOT NULL,
    stored_filename TEXT NOT NULL,
    content_type TEXT,
    insert_after_page INTEGER NOT NULL DEFAULT 1,
    position INTEGER NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS email_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    mission_id INTEGER NOT NULL REFERENCES missions(id) ON DELETE CASCADE,
    to_addresses TEXT NOT NULL,
    cc_addresses TEXT,
    subject TEXT NOT NULL,
    body TEXT,
    status TEXT NOT NULL,
    error_message TEXT,
    sent_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_missions_driver ON missions(driver_id);
CREATE INDEX IF NOT EXISTS idx_missions_date ON missions(mission_date);
CREATE INDEX IF NOT EXISTS idx_legs_mission ON mission_legs(mission_id);
CREATE INDEX IF NOT EXISTS idx_stops_mission ON mission_stops(mission_id);
CREATE INDEX IF NOT EXISTS idx_attachments_mission ON attachments(mission_id);
"""


def get_connection():
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


@contextmanager
def get_db():
    """Context manager pratique : `with get_db() as db:` puis db.execute(...)."""
    conn = get_connection()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def init_db():
    with get_db() as db:
        db.executescript(SCHEMA)
