"""
Amorce la base de données :
  - crée le schéma s'il n'existe pas encore
  - installe les templates OM/BC par défaut (issus de app/templates_data/)
  - avec --demo : ajoute un chauffeur, un véhicule, un client et un ordre
    de mission complet (MARTIN Yannis, 15/09/2026)

La connexion MySQL est lue depuis .env / l'environnement (DATABASE_URL ou
MYSQL_*), exactement comme l'application. Pour amorcer la base de prod
depuis votre machine :

    $env:DATABASE_URL="mysql://user:pass@host:3306/db"; python seed.py --demo

Sur Vercel, plus simple : appeler une fois la route /admin/init?key=SEED_SECRET
(voir README) — aucun accès MySQL requis depuis votre poste.

Usage :
    python seed.py            # schéma + templates par défaut
    python seed.py --demo     # + données de démonstration
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.db import init_db
from app.seeding import seed_templates, seed_demo_data


if __name__ == "__main__":
    init_db(force=True)
    for msg in seed_templates():
        print(msg)
    if "--demo" in sys.argv:
        actions = seed_demo_data()
        for msg in actions:
            print(msg)
        if not actions:
            print("Données de démo non réinjectées (des chauffeurs existent déjà).")
    print("Terminé.")
