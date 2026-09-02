"""
Amorce la base de données :
  - crée le schéma s'il n'existe pas encore
  - installe les templates OM/BC par défaut (issus de app/templates_data/)
    comme templates actifs, si aucun template n'existe déjà
  - avec --demo : ajoute un chauffeur, un véhicule, un client et un ordre
    de mission complet, basés sur l'exemple réel MARTIN Yannis du
    15/09/2026, pour avoir tout de suite quelque chose à explorer

La connexion MySQL est lue depuis .env / l'environnement (DATABASE_URL ou
MYSQL_*), exactement comme l'application. Pour amorcer la base de prod
depuis votre machine :

    DATABASE_URL="mysql://user:pass@host:3306/kent" python seed.py --demo

Usage :
    python seed.py            # schéma + templates par défaut
    python seed.py --demo     # + un chauffeur/véhicule/client/mission de démo
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db import init_db
from app import repo
from app.config import BASE_DIR

TEMPLATES_DIR = BASE_DIR / "app" / "templates_data"


def seed_templates():
    if not repo.list_templates("OM"):
        html = (TEMPLATES_DIR / "om_template.html").read_text(encoding="utf-8")
        repo.create_template("OM", "Ordre de Mission — standard", html, activate=True)
        print("Template OM créé et activé.")
    else:
        print("Template(s) OM déjà présents, rien à faire.")

    if not repo.list_templates("BC"):
        html = (TEMPLATES_DIR / "bc_template.html").read_text(encoding="utf-8")
        repo.create_template("BC", "Billet Collectif — standard", html, activate=True)
        print("Template BC créé et activé.")
    else:
        print("Template(s) BC déjà présents, rien à faire.")


def seed_demo_data():
    if repo.list_drivers():
        print("Des chauffeurs existent déjà, données de démo non réinjectées.")
        return

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
        ("11:00", "13:30", vehicle_id, "Dépôt KENT \u2192 Roissy CDG 2B"),
        ("13:30", "14:00", None, "Pause 30min"),
        ("14:00", "15:50", vehicle_id, "Roissy CDG 2B \u2192 Chartres"),
        ("15:50", "16:00", vehicle_id, "Chartres \u2192 Barjouville"),
        ("16:00", "16:30", vehicle_id, "Barjouville \u2192 Bonneval"),
        ("16:30", "17:30", vehicle_id, "Bonneval \u2192 Mer"),
        ("17:30", "18:30", vehicle_id, "Mer \u2192 Valen\u00e7ay"),
        ("18:30", "18:45", None, "Pause 15min"),
        ("18:45", "20:30", vehicle_id, "Valen\u00e7ay \u2192 D\u00e9p\u00f4t KENT"),
        ("20:30", "20:30", vehicle_id, "Fin de service - D\u00e9p\u00f4t KENT"),
    ]
    stops = [
        ("prise_en_charge", "13:00", "A\u00e9roport Roissy CDG 2B", "", 7),
        ("depose", "15:50", "13 Bis Route de Voves", "CHARTRES", 1),
        ("depose", "16:00", "2 Rue du Hotbrou", "BARJOUVILLE", 1),
        ("depose", "16:30", "6 La Jouanni\u00e8re", "BONNEVAL", 2),
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
    print(f"Chauffeur, véhicule, client et mission de démonstration créés (mission #{mission_id}).")


if __name__ == "__main__":
    init_db()
    seed_templates()
    if "--demo" in sys.argv:
        seed_demo_data()
    print("Terminé.")
