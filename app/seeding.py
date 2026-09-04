"""
Amorçage de la base, réutilisable :
- depuis la ligne de commande (`python seed.py`)
- depuis la route protégée /admin/init (pratique sur Vercel : pas besoin
  d'un accès MySQL depuis votre poste, seule la fonction serverless doit
  joindre la base)
"""
from app import repo
from app.config import BASE_DIR

TEMPLATES_DIR = BASE_DIR / "app" / "templates_data"


def seed_templates():
    """Installe les templates OM/BC par défaut s'ils n'existent pas.
    Retourne la liste des actions effectuées."""
    done = []
    if not repo.list_templates("OM"):
        html = (TEMPLATES_DIR / "om_template.html").read_text(encoding="utf-8")
        repo.create_template("OM", "Ordre de Mission — standard", html, activate=True)
        done.append("template OM créé")
    if not repo.list_templates("BC"):
        html = (TEMPLATES_DIR / "bc_template.html").read_text(encoding="utf-8")
        repo.create_template("BC", "Billet Collectif — standard", html, activate=True)
        done.append("template BC créé")
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
