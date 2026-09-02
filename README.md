# OM+BC — Transports KENT

Application interne pour créer, stocker, modifier et envoyer les **Ordres
de Mission (OM)** et **Billets Collectifs (BC)** de Transports KENT, à
partir des chauffeurs, véhicules et clients enregistrés.

## Ce que ça fait

- **Chauffeurs / Véhicules / Clients** : liste + fiche détail + CRUD complet.
  Les chauffeurs et véhicules alimentent des menus déroulants partout où
  ils sont utilisés (plus de saisie libre).
- **Ordres de mission** : un formulaire unique avec
  - les **arrêts du Billet Collectif** (prises en charge / déposes, adresses, horaires, nb de voyageurs),
  - les **trajets de l'Ordre de Mission** (Début / Fin / Véhicule / Trajet), avec un bouton
    « Générer les trajets depuis les arrêts » qui pré-remplit le tableau OM à partir des arrêts BC
    (vous ajustez ensuite pauses et libellés).
- **Génération PDF** : un seul PDF = **OM (page 1) + pièces jointes + BC**, fusionnés automatiquement.
  Vous pouvez joindre un ou plusieurs fichiers (PDF, PNG, JPG — typiquement le plan de dépose/ramassage
  d'origine) et choisir où les insérer : avant l'OM, entre l'OM et le BC (page 2, par défaut — comme
  dans vos documents actuels), ou après le BC.
- **Envoi par email** : au chauffeur (email pré-rempli, modifiable) + destinataires libres en copie,
  objet et corps personnalisables, PDF généré à la volée en pièce jointe.
- **Templates OM / BC modifiables** : le HTML/Jinja2 qui génère les PDF est stocké **en base**, éditable
  depuis Templates → (modifier le texte, les libellés, la mise en page) → Aperçu avec des données de
  démo → Enregistrer / Activer. Vous pouvez dupliquer un template pour tester une variante sans toucher
  à celui utilisé en production.

## Stack technique — et pourquoi

Le prototype existant (`api/`, `server.js`, Node/Express + Handlebars +
Puppeteer + pdf-lib + nodemailer/msal) n'a pas pu être exploré en détail :
GitHub bloque l'exploration automatisée des dossiers pour ce fetcher
(`tree/...` renvoie *robots disallowed*), donc seuls `package.json`,
`.env.example` et `server.js` (racine) ont pu être lus. Si vous avez un
schéma existant (`scripts/init-db.js` ou équivalent) que vous voulez que
je reprenne à l'identique, envoyez-le-moi et j'aligne le schéma ci-dessous.

Cette version est réécrite en **Python / Flask**, pour une raison très
concrète : dans mon environnement de développement (sandbox sans accès
réseau npm), je ne pouvais ni installer `puppeteer` (téléchargement de
Chromium) ni tester quoi que ce soit côté Node. Le sandbox Python, lui,
avait déjà `Flask`, `reportlab`, `pypdf`, `Pillow`, ainsi que le binaire
système `wkhtmltopdf` — de quoi construire et **tester réellement** toute
la chaîne (génération, fusion PDF, upload, emails) plutôt que d'écrire du
code Node à l'aveugle. Le principe reste le même que votre prototype :
**gabarits HTML → PDF**, exactement ce que vous connaissez.

| Besoin | Choix | Pourquoi |
|---|---|---|
| Serveur web | **Flask** | Déjà disponible, simple, pas de build step côté front (pages rendues en Jinja2 + un peu de JS vanilla pour les lignes dynamiques). |
| Base de données | **SQLite** (`sqlite3`, stdlib) | Zéro dépendance, un seul fichier. Le schéma (`app/db.py`) est écrit en SQL portable ; passer à PostgreSQL plus tard = remplacer `db.py` par un driver `psycopg` sans toucher au reste (`app/repo.py` isole tout le SQL). |
| Templates OM/BC | **HTML + Jinja2**, stockés en base (table `templates`) | Vous avez cité HTML dans les outils que vous connaissez ; Jinja2 est l'équivalent Python de Handlebars. ReportBro et RML restent des options — voir plus bas. |
| HTML → PDF | **wkhtmltopdf** (binaire système, appelé en sous-processus) | Rendu fidèle CSS (tableaux, polices, logo en base64), aucune dépendance Python fragile, testé de bout en bout avec vos 2 PDF d'exemple. |
| Fusion OM + pièces jointes + BC | **pypdf** | Standard, simple, testé avec PDF et image en pièce jointe. |
| Email | **smtplib** (stdlib) + option **MSAL/OAuth2** pour Microsoft 365 | Votre prototype avait déjà un flux O365 OAuth (`msal`, scripts `get-smtp-token`) — repris à l'identique en Python dans `email_service.py`, activable via `SMTP_AUTH_METHOD=oauth2_o365`. |

**Sur ReportBro / RML** : je ne les ai pas utilisés ici. Le format JSON de
ReportBro n'est fiable à écrire qu'avec son designer visuel (que je n'ai
pas dans ce sandbox) ; RML (`z3c.rml`) est une bonne option mais ajoute une
dépendance non testable ici faute de réseau. Le HTML/Jinja2 fait le même
travail et j'ai pu le vérifier visuellement contre vos documents réels
(voir captures dans la conversation). Si vous préférez malgré tout
ReportBro (son designer graphique a un vrai intérêt pour une équipe non
technique), l'architecture s'y prête : `pdf_service.render_template_string()`
est le seul point à remplacer par un appel à `reportbro-lib`, le reste
(stockage en base, CRUD, fusion, email) ne change pas.

## Schéma de données

```
drivers        chauffeurs (nom, prénom, email, tél, actif...)
vehicles       véhicules (nom interne, immatriculation, places, actif...)
clients        donneurs d'ordre (Simplon Voyages...), réutilisables
templates      gabarits OM/BC (type, html, version, actif)
missions       un OM+BC (chauffeur, date, motif, client, statut...)
mission_legs   lignes du tableau "Mission" de l'OM (début/fin/véhicule/trajet)
mission_stops  lignes du tableau du BC (prise en charge/dépose, adresse, voyageurs)
attachments    fichiers joints à une mission + position d'insertion
email_log      historique des envois (destinataires, objet, statut)
```

Détail complet dans `app/db.py`.

## Installation

**Prérequis :** Python 3.10+, et le binaire **wkhtmltopdf** :

- macOS : `brew install --cask wkhtmltopdf`
- Ubuntu/Debian : `sudo apt install wkhtmltopdf`
- Windows : [installeur officiel](https://wkhtmltopdf.org/downloads.html)

```bash
cd ombc-kent
python3 -m venv .venv && source .venv/bin/activate   # Windows : .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # puis éditez SMTP_USER / SMTP_PASS etc.
python seed.py --demo       # crée les templates + un exemple complet (Yannis Martin, 15/09)
python run.py
```

Ouvrez http://localhost:8000 — l'exemple de démo est prêt à être ouvert,
généré en PDF et (si vous avez configuré le SMTP) envoyé par email.

Sans `--demo`, `python seed.py` installe uniquement les deux templates
par défaut (indispensables) sans données factices.

## Configuration email

Deux modes dans `.env` (voir `.env.example` pour le détail complet) :

- `SMTP_AUTH_METHOD=basic` (par défaut) : `SMTP_HOST/PORT/USER/PASS` classiques — fonctionne avec
  Gmail (mot de passe d'application), OVH, Infomaniak...
- `SMTP_AUTH_METHOD=oauth2_o365` : pour Microsoft 365 / Exchange Online (authentification par mot de
  passe désactivée par Microsoft). Nécessite `pip install -r requirements-optional.txt` (paquet `msal`)
  et les identifiants d'une app enregistrée dans Entra ID (`O365_TENANT_ID`, `O365_CLIENT_ID`,
  `O365_CLIENT_SECRET`, `O365_SENDER_EMAIL`).

Le code SMTP a un timeout de 20s : un serveur mail injoignable échoue proprement (message d'erreur
affiché + inscrit dans l'historique) plutôt que de bloquer l'application.

## Aller plus loin

- **PostgreSQL** : remplacer `sqlite3.connect(...)` dans `app/db.py` par un driver Postgres
  (`psycopg`). Le SQL du schéma est déjà portable (types simples, pas de fonctions SQLite-only).
- **Éditeur visuel de templates** : brancher [reportbro-designer](https://github.com/jobsta/reportbro-designer)
  (JS) sur la page Templates, en gardant le stockage en base tel quel — ou migrer le rendu vers
  ReportBro/RML comme expliqué plus haut.
- **Détails passagers** : le schéma `mission_stops` a déjà des colonnes `passenger_name`,
  `passenger_phone`, `booking_ref` (issues du plan de dépose/ramassage d'origine), pas encore exposées
  dans le formulaire pour garder le tableau lisible — faciles à ajouter si utile.
- **Déploiement** : `run.py` utilise le serveur de dev Flask. En production, servez l'app avec
  `gunicorn` (ex. `gunicorn -w 4 -b 0.0.0.0:8000 run:app`) derrière un reverse proxy.

## Arborescence

```
app/
  config.py            configuration (.env)
  db.py                schéma SQLite + connexion
  repo.py              accès aux données (CRUD, SQL brut)
  pdf_service.py        rendu Jinja2 -> HTML -> wkhtmltopdf -> fusion pypdf
  email_service.py      envoi SMTP (basic ou OAuth2 O365)
  utils.py              formats de date/heure en français
  routes/                blueprints Flask (drivers, vehicles, clients, missions, templates_admin)
  templates/              pages Jinja2 (interface web)
  templates_data/         sources HTML/Jinja2 par défaut de l'OM et du BC (utilisées par seed.py)
  static/                 CSS, JS, logo
seed.py                  amorçage (templates + option --demo)
run.py                   point d'entrée
requirements.txt / requirements-optional.txt
.env.example
```
