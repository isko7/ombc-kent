"""
Amorçage de la base, réutilisable :
- depuis la ligne de commande (`python seed.py`)
- depuis la route protégée /admin/init (pratique sur Vercel : pas besoin
  d'un accès MySQL depuis votre poste, seule la fonction serverless doit
  joindre la base)
"""
from app import repo
from app.config import (BASE_DIR, BOOTSTRAP_EMAIL, BOOTSTRAP_FIRST_NAME,
                        BOOTSTRAP_LAST_NAME, BOOTSTRAP_PASSWORD, BOOTSTRAP_USERNAME)

TEMPLATES_DIR = BASE_DIR / "app" / "templates_data"


_DEFAULTS = {
    "OM": ("Ordre de Mission — standard", "om_template.html"),
    "BC": ("Billet Collectif — standard", "bc_template.html"),
}


def seed_templates():
    """Installe les templates OM/BC par défaut s'ils n'existent pas.
    Retourne la liste des actions effectuées."""
    done = []
    for type_, (name, filename) in _DEFAULTS.items():
        if not repo.list_templates(type_):
            html = (TEMPLATES_DIR / filename).read_text(encoding="utf-8")
            repo.create_template(type_, name, html, activate=True)
            done.append(f"template {type_} créé")
    return done


def refresh_default_templates():
    """Remplace le HTML des templates « … — standard » par le contenu
    actuel des fichiers app/templates_data/. ⚠️ écrase les personnalisations
    faites sur ces templates-là (les copies ne sont pas touchées)."""
    done = []
    for type_, (name, filename) in _DEFAULTS.items():
        html = (TEMPLATES_DIR / filename).read_text(encoding="utf-8")
        matches = [t for t in repo.list_templates(type_) if t["name"] == name]
        if matches:
            for t in matches:
                repo.update_template(t["id"], name, html)
                done.append(f"template {type_} #{t['id']} mis à jour")
        else:
            repo.create_template(type_, name, html, activate=True)
            done.append(f"template {type_} créé")
    return done


def seed_demo_data():
    """Ajoute un chauffeur / véhicule / client / mission de démonstration
    (MARTIN Yannis, 15/09/2026). Ne fait rien si des chauffeurs existent."""
    if repo.list_drivers():
        return []

    driver_id = repo.create_driver({
        "last_name": "MARTIN", "first_name": "Yannis",
        "email": "yannis.martin@example.com", "phone": "06 00 00 00 00",
        "active": True,
    })
    vehicle_id = repo.create_vehicle({
        "name": "Navette 3", "plate": "FK-066-ME", "seats": 9, "active": True,
    })
    client_id = repo.create_client({
        "name": "Simplon Voyages", "address": "39 Route de la Libération",
        "postal_code": "41240", "city": "BEAUCE LA ROMAINE", "phone": "06.60.41.54.58",
    })

    legs = [
        ("11:00", "11:00", vehicle_id, "Prise de service - Dépôt KENT"),
        ("11:00", "13:30", vehicle_id, "Dépôt KENT → Roissy CDG 2B"),
        ("13:30", "14:00", None, "Pause 30min"),
        ("14:00", "15:50", vehicle_id, "Roissy CDG 2B → Chartres"),
        ("15:50", "16:00", vehicle_id, "Chartres → Barjouville"),
        ("16:00", "16:30", vehicle_id, "Barjouville → Bonneval"),
        ("16:30", "17:30", vehicle_id, "Bonneval → Mer"),
        ("17:30", "18:30", vehicle_id, "Mer → Valençay"),
        ("18:30", "18:45", None, "Pause 15min"),
        ("18:45", "20:30", vehicle_id, "Valençay → Dépôt KENT"),
        ("20:30", "20:30", vehicle_id, "Fin de service - Dépôt KENT"),
    ]
    stops = [
        ("prise_en_charge", "13:00", "Aéroport Roissy CDG 2B", "", 7),
        ("depose", "15:50", "13 Bis Route de Voves", "CHARTRES", 1),
        ("depose", "16:00", "2 Rue du Hotbrou", "BARJOUVILLE", 1),
        ("depose", "16:30", "6 La Jouannière", "BONNEVAL", 2),
        ("depose", "17:30", "16 Rue d'Alsace", "MER", 2),
        ("depose", "18:30", "18 Rue de la Gare", "VALENCAY", 1),
    ]

    mission_id = repo.create_mission({
        "driver_id": driver_id,
        "mission_date": "2026-09-15",
        "motif": "Transport Occasionnel",
        "client_id": client_id,
        "emission_date": "2026-09-01",
        "status": "brouillon",
        "legs": [
            {"start_time": s, "end_time": e, "vehicle_id": v, "label": l, "is_checkpoint": s == e}
            for (s, e, v, l) in legs
        ],
        "stops": [
            {"stop_type": t, "stop_date": "2026-09-15", "stop_time": tm, "address": a, "city": c,
             "passenger_count": cnt}
            for (t, tm, a, c, cnt) in stops
        ],
    })
    return [f"mission de démo #{mission_id} créée"]


def ensure_login_access():
    """Garantit qu'au moins un chauffeur ADMINISTRATEUR peut se connecter.

    Sans cela, activer l'authentification sur une base existante fermerait
    l'application à tout le monde (les seuls comptes sont des fiches
    chauffeur, et aucune n'a d'identifiants au départ). Si personne n'a
    l'accès, il est donné au chauffeur BOOTSTRAP_* — Ismail KILINC par
    défaut — dont la fiche est créée si elle n'existe pas encore.

    Le compte amorcé est administrateur (voir repo.grant_login) : il doit
    pouvoir rouvrir l'accès aux autres.

    Le critère est bien « un administrateur », pas « un compte » : quand la
    colonne is_admin est ajoutée à une base existante, elle vaut 0 partout,
    et sans cela plus personne ne pourrait administrer l'application. Un
    compte déjà en place est alors simplement promu, son mot de passe est
    conservé.

    Ne fait rien dès qu'un administrateur utilisable existe. Appelée au démarrage
    de l'application, par `python seed.py` et par /admin/init : c'est le
    filet de sécurité si l'accès a été retiré à tout le monde directement
    en base (l'écran Chauffeurs, lui, refuse de retirer le dernier accès).
    Le mot de passe par défaut (BOOTSTRAP_PASSWORD) est à changer dès la
    première connexion.
    """
    from app.auth import hash_password

    if repo.count_admins():
        return []

    label = f"{BOOTSTRAP_FIRST_NAME} {BOOTSTRAP_LAST_NAME}"
    driver = repo.find_driver_by_name(BOOTSTRAP_LAST_NAME, BOOTSTRAP_FIRST_NAME)

    # Le compte existe déjà et fonctionne : on le promeut, sans réinitialiser
    # un mot de passe que son propriétaire utilise peut-être déjà.
    if driver and driver.get("can_login") and driver.get("active") and driver.get("password_hash"):
        repo.set_admin(driver["id"], True)
        return [f"droits d'administration donnés à {label} "
                f"(compte existant « {driver['username']} », mot de passe inchangé)"]

    created = False
    if not driver:
        driver_id = repo.create_driver({
            "last_name": BOOTSTRAP_LAST_NAME, "first_name": BOOTSTRAP_FIRST_NAME,
            "email": BOOTSTRAP_EMAIL, "active": True,
        })
        created = True
    else:
        driver_id = driver["id"]

    username = BOOTSTRAP_USERNAME
    if repo.username_taken(username, exclude_driver_id=driver_id):
        username = f"{username}{driver_id}"
    repo.grant_login(driver_id, username, hash_password(BOOTSTRAP_PASSWORD))

    return [f"accès administrateur donné à {label} (identifiant « {username} »"
            f"{', fiche créée' if created else ''})"]
