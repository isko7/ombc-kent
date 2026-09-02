"""Point d'entrée Vercel (fonction serverless Python / WSGI).

Vercel détecte la variable `app` et la sert comme application WSGI.
Toutes les routes sont réécrites vers ce fichier par vercel.json.
"""
import os
import sys

# La racine du dépôt (qui contient le paquet `app/`) doit être sur le path.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import create_app  # noqa: E402

app = create_app()
