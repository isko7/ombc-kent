"""
Couche d'accès aux données : une fonction par opération, en SQL brut.

Pas d'ORM (pour rester sur des dépendances minimales) : le schéma est
assez simple pour que ce soit lisible tel quel. Le curseur MySQL renvoie
déjà des dict (voir app/db.py) ; `row_to_dict` / `rows_to_dicts` restent
là pour découpler les templates du pilote.
"""
from datetime import datetime, date
from app.db import get_db


def row_to_dict(row):
    return dict(row) if row is not None else None


def rows_to_dicts(rows):
    return [dict(r) for r in rows]


def now_iso():
    return datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")


# ---------------------------------------------------------------- drivers
def list_drivers(include_inactive=True):
    with get_db() as db:
        q = "SELECT * FROM drivers"
        if not include_inactive:
            q += " WHERE active = 1"
        q += " ORDER BY last_name, first_name"
        return rows_to_dicts(db.execute(q).fetchall())


def get_driver(driver_id):
    with get_db() as db:
        return row_to_dict(db.execute("SELECT * FROM drivers WHERE id = ?", (driver_id,)).fetchone())


def create_driver(data):
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO drivers (last_name, first_name, email, phone, license_number, active, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (data["last_name"], data["first_name"], data["email"], data.get("phone"),
             data.get("license_number"), 1 if data.get("active", True) else 0, data.get("notes")),
        )
        return cur.lastrowid


def update_driver(driver_id, data):
    with get_db() as db:
        db.execute(
            """UPDATE drivers SET last_name=?, first_name=?, email=?, phone=?, license_number=?,
               active=?, notes=?, updated_at=? WHERE id=?""",
            (data["last_name"], data["first_name"], data["email"], data.get("phone"),
             data.get("license_number"), 1 if data.get("active", True) else 0, data.get("notes"),
             now_iso(), driver_id),
        )


def delete_driver(driver_id):
    with get_db() as db:
        db.execute("DELETE FROM drivers WHERE id = ?", (driver_id,))


# --------------------------------------------------------------- vehicles
def list_vehicles(include_inactive=True):
    with get_db() as db:
        q = "SELECT * FROM vehicles"
        if not include_inactive:
            q += " WHERE active = 1"
        q += " ORDER BY name, plate"
        return rows_to_dicts(db.execute(q).fetchall())


def get_vehicle(vehicle_id):
    with get_db() as db:
        return row_to_dict(db.execute("SELECT * FROM vehicles WHERE id = ?", (vehicle_id,)).fetchone())


def create_vehicle(data):
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO vehicles (name, plate, seats, active, notes) VALUES (?, ?, ?, ?, ?)""",
            (data.get("name"), data["plate"], data.get("seats") or None,
             1 if data.get("active", True) else 0, data.get("notes")),
        )
        return cur.lastrowid


def update_vehicle(vehicle_id, data):
    with get_db() as db:
        db.execute(
            """UPDATE vehicles SET name=?, plate=?, seats=?, active=?, notes=?, updated_at=?
               WHERE id=?""",
            (data.get("name"), data["plate"], data.get("seats") or None,
             1 if data.get("active", True) else 0, data.get("notes"), now_iso(), vehicle_id),
        )


def delete_vehicle(vehicle_id):
    with get_db() as db:
        db.execute("DELETE FROM vehicles WHERE id = ?", (vehicle_id,))


# ---------------------------------------------------------------- clients
def list_clients():
    with get_db() as db:
        return rows_to_dicts(db.execute("SELECT * FROM clients ORDER BY name").fetchall())


def get_client(client_id):
    with get_db() as db:
        return row_to_dict(db.execute("SELECT * FROM clients WHERE id = ?", (client_id,)).fetchone())


def create_client(data):
    with get_db() as db:
        cur = db.execute(
            """INSERT INTO clients (name, address, postal_code, city, phone, email, notes)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (data["name"], data.get("address"), data.get("postal_code"), data.get("city"),
             data.get("phone"), data.get("email"), data.get("notes")),
        )
        return cur.lastrowid


def update_client(client_id, data):
    with get_db() as db:
        db.execute(
            """UPDATE clients SET name=?, address=?, postal_code=?, city=?, phone=?, email=?,
               notes=?, updated_at=? WHERE id=?""",
            (data["name"], data.get("address"), data.get("postal_code"), data.get("city"),
             data.get("phone"), data.get("email"), data.get("notes"), now_iso(), client_id),
        )


def delete_client(client_id):
    with get_db() as db:
        db.execute("DELETE FROM clients WHERE id = ?", (client_id,))


# -------------------------------------------------------------- templates
def list_templates(type_=None):
    with get_db() as db:
        if type_:
            rows = db.execute(
                "SELECT * FROM templates WHERE type = ? ORDER BY updated_at DESC", (type_,)
            ).fetchall()
        else:
            rows = db.execute("SELECT * FROM templates ORDER BY type, updated_at DESC").fetchall()
        return rows_to_dicts(rows)


def get_template(template_id):
    with get_db() as db:
        return row_to_dict(db.execute("SELECT * FROM templates WHERE id = ?", (template_id,)).fetchone())


def get_active_template(type_):
    with get_db() as db:
        return row_to_dict(
            db.execute(
                "SELECT * FROM templates WHERE type = ? AND is_active = 1 ORDER BY id DESC LIMIT 1",
                (type_,),
            ).fetchone()
        )


def create_template(type_, name, definition_html, activate=False):
    with get_db() as db:
        if activate:
            db.execute("UPDATE templates SET is_active = 0 WHERE type = ?", (type_,))
        cur = db.execute(
            """INSERT INTO templates (type, name, is_active, definition_html, version)
               VALUES (?, ?, ?, ?, 1)""",
            (type_, name, 1 if activate else 0, definition_html),
        )
        return cur.lastrowid


def update_template(template_id, name, definition_html):
    with get_db() as db:
        db.execute(
            """UPDATE templates SET name=?, definition_html=?, version=version+1, updated_at=?
               WHERE id=?""",
            (name, definition_html, now_iso(), template_id),
        )


def activate_template(template_id):
    with get_db() as db:
        row = db.execute("SELECT type FROM templates WHERE id=?", (template_id,)).fetchone()
        if not row:
            return
        db.execute("UPDATE templates SET is_active = 0 WHERE type = ?", (row["type"],))
        db.execute("UPDATE templates SET is_active = 1 WHERE id = ?", (template_id,))


# --------------------------------------------------------------- missions
def _next_reference(db, mission_date_str):
    year = mission_date_str[:4] if mission_date_str else str(date.today().year)
    count = db.execute(
        "SELECT COUNT(*) AS c FROM missions WHERE reference LIKE ?", (f"OM-{year}-%",)
    ).fetchone()["c"]
    return f"OM-{year}-{count + 1:04d}"


def list_missions(driver_id=None, date_from=None, date_to=None, status=None):
    with get_db() as db:
        q = """SELECT m.*, d.last_name AS driver_last_name, d.first_name AS driver_first_name,
                      c.name AS client_name
               FROM missions m
               JOIN drivers d ON d.id = m.driver_id
               LEFT JOIN clients c ON c.id = m.client_id
               WHERE 1=1"""
        params = []
        if driver_id:
            q += " AND m.driver_id = ?"
            params.append(driver_id)
        if date_from:
            q += " AND m.mission_date >= ?"
            params.append(date_from)
        if date_to:
            q += " AND m.mission_date <= ?"
            params.append(date_to)
        if status:
            q += " AND m.status = ?"
            params.append(status)
        q += " ORDER BY m.mission_date DESC, m.id DESC"
        return rows_to_dicts(db.execute(q, params).fetchall())


def get_mission(mission_id):
    with get_db() as db:
        mission = row_to_dict(db.execute("SELECT * FROM missions WHERE id = ?", (mission_id,)).fetchone())
        if not mission:
            return None
        mission["driver"] = row_to_dict(
            db.execute("SELECT * FROM drivers WHERE id = ?", (mission["driver_id"],)).fetchone()
        )
        mission["client"] = row_to_dict(
            db.execute("SELECT * FROM clients WHERE id = ?", (mission["client_id"],)).fetchone()
        ) if mission["client_id"] else None
        legs = db.execute(
            """SELECT l.*, v.plate AS vehicle_plate, v.name AS vehicle_name
               FROM mission_legs l LEFT JOIN vehicles v ON v.id = l.vehicle_id
               WHERE l.mission_id = ? ORDER BY l.position""",
            (mission_id,),
        ).fetchall()
        mission["legs"] = rows_to_dicts(legs)
        stops = db.execute(
            "SELECT * FROM mission_stops WHERE mission_id = ? ORDER BY position", (mission_id,)
        ).fetchall()
        mission["stops"] = rows_to_dicts(stops)
        # Métadonnées seulement : le contenu (LONGBLOB) est chargé à la
        # demande par le service PDF via list_attachment_contents().
        attachments = db.execute(
            """SELECT id, mission_id, filename, content_type, insert_after_page, position, created_at
               FROM attachments WHERE mission_id = ? ORDER BY position""",
            (mission_id,),
        ).fetchall()
        mission["attachments"] = rows_to_dicts(attachments)
        return mission


def list_attachment_contents(mission_id):
    """Pièces jointes d'une mission avec leur contenu binaire, triées."""
    with get_db() as db:
        return rows_to_dicts(
            db.execute(
                "SELECT * FROM attachments WHERE mission_id = ? ORDER BY position", (mission_id,)
            ).fetchall()
        )


def create_mission(data):
    with get_db() as db:
        reference = _next_reference(db, data["mission_date"])
        cur = db.execute(
            """INSERT INTO missions (reference, driver_id, mission_date, motif, remarks, client_id,
               emission_date, price, status, om_template_id, bc_template_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (reference, data["driver_id"], data["mission_date"], data.get("motif") or "Transport Occasionnel",
             data.get("remarks"), data.get("client_id") or None, data.get("emission_date"),
             data.get("price"), data.get("status") or "brouillon",
             data.get("om_template_id") or None, data.get("bc_template_id") or None),
        )
        mission_id = cur.lastrowid
        _replace_legs(db, mission_id, data.get("legs") or [])
        _replace_stops(db, mission_id, data.get("stops") or [])
        return mission_id


def duplicate_mission(mission_id):
    """Crée une copie de la mission (nouvelle référence, statut réinitialisé
    à « brouillon », trajets/arrêts recopiés). Les pièces jointes et
    l'historique d'envoi ne sont pas dupliqués. Renvoie le nouvel id."""
    src = get_mission(mission_id)
    if not src:
        return None
    return create_mission({
        "driver_id": src["driver_id"],
        "mission_date": src["mission_date"],
        "motif": src["motif"],
        "remarks": src["remarks"],
        "client_id": src["client_id"],
        "emission_date": src["emission_date"],
        "price": src["price"],
        "status": "brouillon",
        "om_template_id": src["om_template_id"],
        "bc_template_id": src["bc_template_id"],
        "legs": [
            {"start_time": l["start_time"], "end_time": l["end_time"], "vehicle_id": l["vehicle_id"],
             "label": l["label"], "is_checkpoint": l["is_checkpoint"], "is_relay": l.get("is_relay"),
             "relay_driver_id": l.get("relay_driver_id")}
            for l in src["legs"]
        ],
        "stops": [
            {"stop_type": s["stop_type"], "stop_date": s["stop_date"], "stop_time": s["stop_time"],
             "address": s["address"], "city": s["city"], "passenger_count": s["passenger_count"],
             "passenger_name": s["passenger_name"], "passenger_phone": s["passenger_phone"],
             "booking_ref": s["booking_ref"]}
            for s in src["stops"]
        ],
    })


def update_mission(mission_id, data):
    with get_db() as db:
        db.execute(
            """UPDATE missions SET driver_id=?, mission_date=?, motif=?, remarks=?, client_id=?,
               emission_date=?, price=?, status=?, om_template_id=?, bc_template_id=?, updated_at=?
               WHERE id=?""",
            (data["driver_id"], data["mission_date"], data.get("motif") or "Transport Occasionnel",
             data.get("remarks"), data.get("client_id") or None, data.get("emission_date"),
             data.get("price"), data.get("status") or "brouillon",
             data.get("om_template_id") or None, data.get("bc_template_id") or None,
             now_iso(), mission_id),
        )
        _replace_legs(db, mission_id, data.get("legs") or [])
        _replace_stops(db, mission_id, data.get("stops") or [])


def _replace_legs(db, mission_id, legs):
    db.execute("DELETE FROM mission_legs WHERE mission_id = ?", (mission_id,))
    for i, leg in enumerate(legs):
        db.execute(
            """INSERT INTO mission_legs (mission_id, position, start_time, end_time, vehicle_id,
               label, is_checkpoint, is_relay, relay_driver_id)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mission_id, i, leg["start_time"], leg["end_time"], leg.get("vehicle_id") or None,
             leg["label"], 1 if leg.get("is_checkpoint") else 0,
             1 if leg.get("is_relay") else 0, leg.get("relay_driver_id") or None),
        )


def _replace_stops(db, mission_id, stops):
    db.execute("DELETE FROM mission_stops WHERE mission_id = ?", (mission_id,))
    for i, stop in enumerate(stops):
        db.execute(
            """INSERT INTO mission_stops (mission_id, position, stop_type, stop_date, stop_time,
               address, city, passenger_count, passenger_name, passenger_phone, booking_ref)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (mission_id, i, stop["stop_type"], stop["stop_date"], stop["stop_time"], stop["address"],
             stop.get("city"), stop.get("passenger_count") or 1, stop.get("passenger_name"),
             stop.get("passenger_phone"), stop.get("booking_ref")),
        )


def delete_mission(mission_id):
    # Pas de FK ON DELETE CASCADE (schéma sans contraintes) -> on supprime
    # explicitement les lignes filles.
    with get_db() as db:
        for table in ("mission_legs", "mission_stops", "attachments", "email_log"):
            db.execute(f"DELETE FROM {table} WHERE mission_id = ?", (mission_id,))
        db.execute("DELETE FROM missions WHERE id = ?", (mission_id,))


def set_mission_status(mission_id, status):
    with get_db() as db:
        db.execute("UPDATE missions SET status=?, updated_at=? WHERE id=?", (status, now_iso(), mission_id))


# ------------------------------------------------------------ attachments
def add_attachment(mission_id, filename, content, content_type, insert_after_page):
    """`content` : octets bruts du fichier (stockés en LONGBLOB)."""
    with get_db() as db:
        max_pos = db.execute(
            "SELECT COALESCE(MAX(position), -1) AS m FROM attachments WHERE mission_id = ?", (mission_id,)
        ).fetchone()["m"]
        cur = db.execute(
            """INSERT INTO attachments (mission_id, filename, content, content_type,
               insert_after_page, position) VALUES (?, ?, ?, ?, ?, ?)""",
            (mission_id, filename, content, content_type, insert_after_page, max_pos + 1),
        )
        return cur.lastrowid


def get_attachment(attachment_id):
    with get_db() as db:
        return row_to_dict(db.execute("SELECT * FROM attachments WHERE id = ?", (attachment_id,)).fetchone())


def delete_attachment(attachment_id):
    with get_db() as db:
        db.execute("DELETE FROM attachments WHERE id = ?", (attachment_id,))


# ------------------------------------------------------------- email log
def log_email(mission_id, to_addresses, cc_addresses, subject, body, status, error_message=None):
    with get_db() as db:
        db.execute(
            """INSERT INTO email_log (mission_id, to_addresses, cc_addresses, subject, body, status,
               error_message) VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (mission_id, to_addresses, cc_addresses, subject, body, status, error_message),
        )


def list_email_log(mission_id):
    with get_db() as db:
        return rows_to_dicts(
            db.execute(
                "SELECT * FROM email_log WHERE mission_id = ? ORDER BY sent_at DESC", (mission_id,)
            ).fetchall()
        )
