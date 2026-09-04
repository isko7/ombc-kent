# OM+BC — Transports KENT

Application interne pour créer, stocker, modifier et envoyer les **Ordres
de Mission (OM)** et **Billets Collectifs (BC)** de Transports KENT, à
partir des chauffeurs, véhicules et clients enregistrés.

Déployée sur **Vercel** (fonctions serverless), base **MySQL**.

## Ce que ça fait

- **Chauffeurs / Véhicules / Clients** : liste + fiche + CRUD complet. Ils
  alimentent les menus déroulants partout où ils sont utilisés.
- **Ordres de mission** : un formulaire unique avec les **arrêts du Billet
  Collectif** (prises en charge / déposes, adresses, horaires, voyageurs) et
  les **trajets de l'Ordre de Mission** (début / fin / véhicule / trajet),
  avec un bouton « Générer les trajets depuis les arrêts ».
- **Génération PDF** : un seul PDF = **OM + pièces jointes + BC**, fusionnés.
  Pièces jointes (PDF/PNG/JPG) insérables avant l'OM, entre l'OM et le BC
  (page 2, par défaut), ou après le BC.
- **Envoi par email** : au chauffeur + destinataires en copie, objet et corps
  personnalisables, PDF en pièce jointe, historique des envois.
- **Templates OM / BC modifiables** : le HTML/Jinja2 qui génère les PDF est
  stocké en base, éditable depuis *Templates* (aperçu sur données de démo,
  duplication pour tester une variante).

## Stack technique

L'application est écrite en **Python / Flask**. Principe : **gabarits HTML
→ PDF**, avec la base de données comme source unique des chauffeurs,
véhicules, clients et missions.

| Besoin | Choix | Détail |
|---|---|---|
| Hébergement | **Vercel** | `api/index.py` sert l'app Flask (WSGI) ; `vercel.json` réécrit toutes les routes vers cette fonction. |
| Serveur web | **Flask** | Pas de build front : pages en Jinja2 + JS vanilla. |
| Base de données | **MySQL** (`PyMySQL`, pur Python) | Connexion via `DATABASE_URL`. Schéma dans `app/db.py`, accès aux données isolé dans `app/repo.py`. |
| Templates OM/BC | **HTML + Jinja2**, stockés en base (table `templates`) | Éditables depuis l'interface. |
| HTML → PDF | **Chrome headless** (`api/render_pdf.js`, `@sparticuz/chromium`) | 2ᵉ fonction serverless Node, appelée en HTTP interne par Flask. Les règles CSS `@page` des templates sont respectées (`preferCSSPageSize`). En local : `wkhtmltopdf`. |
| Fusion OM + PJ + BC | **pypdf** | Les pièces jointes sont stockées en base (`LONGBLOB`). |
| Email | **smtplib** (stdlib) + option **MSAL/OAuth2** pour Microsoft 365 | `SMTP_AUTH_METHOD=basic` ou `oauth2_o365`. |

## Schéma de données

```
drivers        chauffeurs
vehicles       véhicules
clients        donneurs d'ordre, réutilisables
templates      gabarits OM/BC (type, html, version, actif)
missions       un OM+BC (chauffeur, date, motif, client, statut...)
mission_legs   lignes du tableau « Mission » de l'OM
mission_stops  lignes du tableau du BC
attachments    fichiers joints (contenu binaire + position d'insertion)
email_log      historique des envois
```

Détail complet dans `app/db.py` (`SCHEMA_STATEMENTS`).

---

## Déploiement sur Vercel

### 1. Base de données MySQL

Provisionner un MySQL accessible depuis Internet (offres compatibles :
PlanetScale, Aiven, Railway, un MySQL managé OVH/Scaleway, ou la marketplace
Vercel). Récupérer une URL de connexion de la forme :

```
mysql://utilisateur:motdepasse@hote:3306/nom_de_base
```

### 2. Variables d'environnement Vercel

Dans *Project → Settings → Environment Variables* :

| Variable | Valeur |
|---|---|
| `DATABASE_URL` | l'URL MySQL ci-dessus (ou les variables `MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` / `MYSQL_DATABASE` / `MYSQL_SSL` séparées — à préférer si le mot de passe contient `@` ou des espaces) |
| `PDF_ENGINE` | `http` |
| `PDF_RENDER_SECRET` | une chaîne aléatoire (partagée entre les 2 fonctions, définie une seule fois ici) |
| `SECRET_KEY` | une chaîne aléatoire |
| `SEED_SECRET` | une chaîne aléatoire (pour la route d'initialisation, voir §3) |
| `SMTP_AUTH_METHOD` | `basic` (ou `oauth2_o365`) |
| `SMTP_HOST` / `SMTP_PORT` / `SMTP_USER` / `SMTP_PASS` | identifiants SMTP |
| `SMTP_FROM_NAME` / `SMTP_FROM_EMAIL` | expéditeur affiché |
| `COMPANY_*`, `OM_LEGAL_REF`, `BC_LEGAL_REF` | si différent des valeurs par défaut (voir `.env.example`) |

### Microsoft 365 / Exchange Online (`SMTP_AUTH_METHOD=oauth2_o365`)

O365 a désactivé l'authentification SMTP par mot de passe : il faut une
App Registration Azure AD avec permission d'envoi applicative.

1. **portal.azure.com → Azure Active Directory → App registrations → New
   registration** (ou réutiliser une app existante).
2. Notez l'**Application (client) ID** et le **Directory (tenant) ID**
   (page *Overview*).
3. **Certificates & secrets → New client secret** → copiez la **Value**
   tout de suite (affichée une seule fois).
4. **API permissions → Add a permission → APIs my organization uses**
   → cherchez *Office 365 Exchange Online* → **Application permissions**
   → cochez **`SMTP.SendAsApp`** → Add → puis **Grant admin consent**
   (nécessite un rôle Admin global / Exchange).
5. **Activer l'authentification SMTP sur la boîte mail** qui enverra les
   emails (désactivée par défaut sur O365) : Exchange admin center →
   Recipients → Mailboxes → la boîte → *Manage email apps* → activer
   *Authenticated SMTP*. Ou en PowerShell :
   ```powershell
   Set-CASMailbox -Identity expediteur@votredomaine.com -SmtpClientAuthenticationDisabled $false
   ```
6. *(Recommandé)* Restreindre l'app à cette seule boîte mail plutôt que
   tout le tenant, via une Application Access Policy (Exchange Online
   PowerShell) :
   ```powershell
   New-DistributionGroup -Name "KentSmtpSenders" -Members expediteur@votredomaine.com
   New-ApplicationAccessPolicy -AppId <client-id> -PolicyScopeGroupId KentSmtpSenders@votredomaine.com -AccessRight RestrictAccess -Description "Limite KENT SMTP à l'expéditeur"
   ```
7. Variables (Vercel ou `.env`) :
   ```
   SMTP_AUTH_METHOD=oauth2_o365
   O365_TENANT_ID=<Directory (tenant) ID>
   O365_CLIENT_ID=<Application (client) ID>
   O365_CLIENT_SECRET=<Value du secret, pas l'ID>
   O365_SENDER_EMAIL=expediteur@votredomaine.com
   SMTP_HOST=smtp.office365.com
   SMTP_PORT=587
   SMTP_FROM_EMAIL=expediteur@votredomaine.com
   ```
   `msal` (le paquet OAuth2) est déjà dans `requirements.txt`, aucune
   installation supplémentaire n'est nécessaire.

> **Protection de déploiement** : si l'authentification Vercel (Deployment
> Protection) est active, l'appel interne Flask → `/api/render_pdf` est
> bloqué. Soit la désactiver, soit garder `PDF_RENDER_SECRET` **et** ajouter
> l'en-tête de contournement via `VERCEL_AUTOMATION_BYPASS_SECRET`.

### 3. Amorcer la base

Le schéma se crée tout seul au premier démarrage (`CREATE TABLE IF NOT
EXISTS`), mais il faut installer les **templates OM/BC par défaut** une fois.

**Option simple (Vercel) — aucun accès MySQL requis depuis votre poste :**
après le 1ᵉʳ déploiement, ouvrir une fois dans le navigateur :

```
https://<projet>.vercel.app/admin/init?key=<SEED_SECRET>          # schéma + templates
https://<projet>.vercel.app/admin/init?key=<SEED_SECRET>&demo=1   # + mission de démo
```

La réponse est un JSON listant les actions. La route est idempotente et
répond 404 si `SEED_SECRET` n'est pas défini.

**Option ligne de commande** (si votre poste peut joindre la base) :

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
$env:DATABASE_URL="mysql://...:3306/db"; python seed.py --demo
```

### 4. Déployer

`git push` sur la branche suivie par Vercel, ou `vercel --prod`.

---

## Développement local

**Prérequis :** Python 3.10+, un MySQL local (ou distant), et le binaire
**wkhtmltopdf** (rendu PDF local) :

- Windows : `winget install wkhtmltopdf.wkhtmltox`
- macOS : `brew install --cask wkhtmltopdf` · Debian/Ubuntu : `apt install wkhtmltopdf`

```bash
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env        # éditer DATABASE_URL, SMTP_*, etc.
python seed.py --demo
python run.py               # http://localhost:8000
```

En local, `PDF_ENGINE=wkhtmltopdf` (défaut) utilise le binaire système. Pour
tester le rendu Chrome serverless en local, utiliser `vercel dev` avec
`PDF_ENGINE=http`.

## Arborescence

```
api/
  index.py             point d'entrée Vercel (WSGI Flask)
  render_pdf.js        fonction Node : HTML -> PDF (Chrome headless)
app/
  config.py            configuration (.env / variables Vercel)
  db.py               connexion MySQL + schéma
  repo.py             accès aux données (SQL brut)
  pdf_service.py       rendu Jinja2 -> HTML -> PDF -> fusion pypdf
  email_service.py     envoi SMTP (basic ou OAuth2 O365)
  utils.py             formats de date/heure en français
  routes/              blueprints Flask
  templates/           pages Jinja2 (interface web)
  templates_data/      sources HTML/Jinja2 par défaut de l'OM et du BC
  static/              CSS, JS, logo
seed.py                 amorçage (schéma + templates + option --demo)
run.py                  serveur de dev Flask
vercel.json             config des fonctions + réécritures
requirements.txt        dépendances Python
package.json            dépendances Node (fonction de rendu PDF)
.env.example
```
