"""Point d'entrée : `python run.py` lance le serveur de développement Flask."""
from app import create_app
from app.config import PORT, DEBUG

app = create_app()

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=DEBUG, threaded=True)
