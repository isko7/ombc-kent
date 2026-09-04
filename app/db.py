"""
Connexion MySQL + schéma de la base.

On utilise PyMySQL (pilote pur Python : aucune compilation, donc
déployable tel quel sur Vercel). La connexion est réutilisée entre les
invocations « chaudes » de la fonction serverless (un `ping(reconnect=True)`
la ré-ouvre si elle est tombée).

`repo.py` est écrit avec des placeholders SQLite (`?`) ; le petit wrapper
`_Cursor` ci-dessous les traduit en `%s` pour PyMySQL, ce qui garde la
couche d'accès aux données lisible et portable. Aucune requête de `repo.py`
ne contient de `?` ou de `%` littéral, la traduction est donc sûre.
"""
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor

from app.config import DB_CONFIG, env

# Index déclarés en ligne dans les CREATE TABLE (MySQL ne connaît pas
# « CREATE INDEX IF NOT EXISTS »). Pas de contraintes FOREIGN KEY : la
# cohérence référentielle est gérée côté application (repo.py), et les DDL
# de FK sont lents / capricieux sur TiDB serverless. La suppression en
# cascade des lignes filles est faite explicitement dans repo.delete_*.
SCHEMA_STATEMENTS = [
    """
    CREATE TABLE IF NOT EXISTS drivers (
        id INT AUTO_INCREMENT PRIMARY KEY,
        last_name VARCHAR(120) NOT NULL,
        first_name VARCHAR(120) NOT NULL,
        email VARCHAR(255) NOT NULL,
        phone VARCHAR(40),
        license_number VARCHAR(60),
        active TINYINT(1) NOT NULL DEFAULT 1,
        notes TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS vehicles (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(120),
        plate VARCHAR(32) NOT NULL UNIQUE,
        seats INT,
        active TINYINT(1) NOT NULL DEFAULT 1,
        notes TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS clients (
        id INT AUTO_INCREMENT PRIMARY KEY,
        name VARCHAR(255) NOT NULL,
        address VARCHAR(255),
        postal_code VARCHAR(20),
        city VARCHAR(120),
        phone VARCHAR(40),
        email VARCHAR(255),
        notes TEXT,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS templates (
        id INT AUTO_INCREMENT PRIMARY KEY,
        type VARCHAR(4) NOT NULL,
        name VARCHAR(255) NOT NULL,
        is_active TINYINT(1) NOT NULL DEFAULT 0,
        definition_html MEDIUMTEXT NOT NULL,
        version INT NOT NULL DEFAULT 1,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_templates_type (type)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS missions (
        id INT AUTO_INCREMENT PRIMARY KEY,
        reference VARCHAR(64) UNIQUE,
        driver_id INT NOT NULL,
        mission_date VARCHAR(10) NOT NULL,
        motif VARCHAR(255) NOT NULL DEFAULT 'Transport Occasionnel',
        remarks TEXT,
        client_id INT NULL,
        emission_date VARCHAR(10),
        price VARCHAR(60),
        status VARCHAR(30) NOT NULL DEFAULT 'brouillon',
        om_template_id INT NULL,
        bc_template_id INT NULL,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_missions_driver (driver_id),
        KEY idx_missions_date (mission_date)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_legs (
        id INT AUTO_INCREMENT PRIMARY KEY,
        mission_id INT NOT NULL,
        position INT NOT NULL,
        start_time VARCHAR(10) NOT NULL,
        end_time VARCHAR(10) NOT NULL,
        vehicle_id INT NULL,
        label VARCHAR(255) NOT NULL,
        is_checkpoint TINYINT(1) NOT NULL DEFAULT 0,
        KEY idx_legs_mission (mission_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS mission_stops (
        id INT AUTO_INCREMENT PRIMARY KEY,
        mission_id INT NOT NULL,
        position INT NOT NULL,
        stop_type VARCHAR(20) NOT NULL,
        stop_date VARCHAR(10) NOT NULL,
        stop_time VARCHAR(10) NOT NULL,
        address VARCHAR(255) NOT NULL,
        city VARCHAR(120),
        passenger_count INT NOT NULL DEFAULT 1,
        passenger_name VARCHAR(160),
        passenger_phone VARCHAR(40),
        booking_ref VARCHAR(80),
        KEY idx_stops_mission (mission_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS attachments (
        id INT AUTO_INCREMENT PRIMARY KEY,
        mission_id INT NOT NULL,
        filename VARCHAR(255) NOT NULL,
        content_type VARCHAR(120),
        content LONGBLOB NOT NULL,
        insert_after_page INT NOT NULL DEFAULT 1,
        position INT NOT NULL DEFAULT 0,
        created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_attachments_mission (mission_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
    """
    CREATE TABLE IF NOT EXISTS email_log (
        id INT AUTO_INCREMENT PRIMARY KEY,
        mission_id INT NOT NULL,
        to_addresses TEXT NOT NULL,
        cc_addresses TEXT,
        subject VARCHAR(500) NOT NULL,
        body MEDIUMTEXT,
        status VARCHAR(20) NOT NULL,
        error_message TEXT,
        sent_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
        KEY idx_email_mission (mission_id)
    ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4
    """,
]


def _connect():
    cfg = DB_CONFIG
    kwargs = dict(
        host=cfg["host"],
        port=cfg["port"],
        user=cfg["user"],
        password=cfg["password"],
        database=cfg["database"],
        charset="utf8mb4",
        cursorclass=DictCursor,
        autocommit=False,
        # Timeouts courts : sur Vercel une fonction a ~60 s. Mieux vaut une
        # erreur claire tout de suite qu'un FUNCTION_INVOCATION_FAILED.
        connect_timeout=int(env("MYSQL_CONNECT_TIMEOUT", "8")),
        read_timeout=20,
        write_timeout=20,
    )
    if cfg.get("ssl"):
        # ssl={} suffit pour activer TLS sans vérification stricte du CA,
        # ce que la plupart des MySQL managés acceptent.
        kwargs["ssl"] = {}
    return pymysql.connect(**kwargs)


def sanitized_config():
    """Config de connexion sans le mot de passe (pour /admin/dbcheck)."""
    cfg = DB_CONFIG
    return {
        "host": cfg["host"], "port": cfg["port"], "user": cfg["user"],
        "database": cfg["database"], "ssl": cfg["ssl"],
        "password_set": bool(cfg["password"]),
    }


def check_connection():
    """Tente une connexion + SELECT VERSION(). Renvoie un dict de diagnostic."""
    import traceback
    out = {"config": sanitized_config()}
    try:
        conn = _connect()
        with conn.cursor() as cur:
            cur.execute("SELECT VERSION() AS v")
            out["version"] = cur.fetchone()["v"]
        conn.close()
        out["ok"] = True
    except Exception as e:
        out["ok"] = False
        out["error"] = f"{type(e).__name__}: {e}"
        out["trace"] = traceback.format_exc().splitlines()[-5:]
    return out


_conn = None


def _get_conn():
    global _conn
    if _conn is not None:
        try:
            _conn.ping(reconnect=True)
            return _conn
        except Exception:
            try:
                _conn.close()
            except Exception:
                pass
            _conn = None
    _conn = _connect()
    return _conn


class _Cursor:
    """Enveloppe le curseur PyMySQL pour accepter la syntaxe de repo.py :
    `db.execute(sql, params)` renvoie un objet avec .fetchone()/.fetchall()/
    .lastrowid, en traduisant les placeholders `?` en `%s`."""

    def __init__(self, cursor):
        self._c = cursor

    def execute(self, sql, params=None):
        self._c.execute(sql.replace("?", "%s"), tuple(params) if params else None)
        return self

    def fetchone(self):
        return self._c.fetchone()

    def fetchall(self):
        return self._c.fetchall()

    @property
    def lastrowid(self):
        return self._c.lastrowid


@contextmanager
def get_db():
    """`with get_db() as db:` puis db.execute(...). Commit auto en sortie,
    rollback si exception. La connexion reste ouverte (réutilisée à chaud)."""
    conn = _get_conn()
    cur = conn.cursor()
    try:
        yield _Cursor(cur)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()


_initialized = False


def init_db(force=False, report=False):
    """Crée le schéma s'il n'existe pas. Idempotent (CREATE TABLE IF NOT
    EXISTS). Exécuté une fois par process au démarrage de l'app.

    report=True -> renvoie une liste [{table, ms}] au lieu de rien, et
    n'avale pas les exceptions (utile pour /admin/init)."""
    global _initialized
    if _initialized and not force:
        return [] if report else None
    import time
    conn = _get_conn()
    timings = []
    with conn.cursor() as cur:
        for stmt in SCHEMA_STATEMENTS:
            name = stmt.split("IF NOT EXISTS", 1)[-1].split("(", 1)[0].strip()
            t0 = time.monotonic()
            cur.execute(stmt)
            timings.append({"table": name, "ms": round((time.monotonic() - t0) * 1000)})
    conn.commit()
    _initialized = True
    return timings if report else None
