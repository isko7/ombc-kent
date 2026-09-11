"""Petits utilitaires de formatage (dates/heures en français)."""
import unicodedata
from datetime import date, datetime

# Libellé du dépôt utilisé dans les trajets. Ce n'est pas une adresse :
# routing.py lui substitue celle de l'entreprise (COMPANY_* du .env).
DEPOT_LABEL = "Dépôt KENT"

WEEKDAYS_FR = ["Lundi", "Mardi", "Mercredi", "Jeudi", "Vendredi", "Samedi", "Dimanche"]
MONTHS_FR = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet",
             "août", "septembre", "octobre", "novembre", "décembre"]


def parse_iso_date(value):
    """'2026-09-15' -> date(2026, 9, 15). Accepte aussi un objet date/None."""
    if not value:
        return None
    if isinstance(value, date):
        return value
    return datetime.strptime(value[:10], "%Y-%m-%d").date()


def fmt_time(hhmm):
    """'11:00' -> '11h00'. Laisse passer une chaîne déjà au format 11h00."""
    if not hhmm:
        return ""
    return hhmm.replace(":", "h")


def fmt_date_short(value):
    """date ou 'YYYY-MM-DD' -> '15/09/26'."""
    d = parse_iso_date(value)
    return d.strftime("%d/%m/%y") if d else ""


def fmt_date_long(value):
    """date ou 'YYYY-MM-DD' -> '15/09/2026'."""
    d = parse_iso_date(value)
    return d.strftime("%d/%m/%Y") if d else ""


def day_label(value):
    d = parse_iso_date(value)
    return WEEKDAYS_FR[d.weekday()] if d else ""


def fmt_date_full(value):
    """date ou 'YYYY-MM-DD' -> 'mardi 08/09/2026' (jour en minuscule, comme
    dans une phrase — utilisé pour l'objet/corps des emails)."""
    d = parse_iso_date(value)
    return f"{WEEKDAYS_FR[d.weekday()].lower()} {d.strftime('%d/%m/%Y')}" if d else ""


def _fold(text):
    """Minuscules sans accents, pour comparer « Dépôt » et « Depot »."""
    decomposed = unicodedata.normalize("NFD", (text or "").strip().lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def is_depot(text):
    """Vrai si le libellé désigne le dépôt, quelle que soit la casse ou la
    présence des accents (la génération automatique écrit « Dépôt KENT »,
    mais une saisie manuelle peut donner « Depot KENT »)."""
    return _fold(text) == _fold(DEPOT_LABEL)


def shuttle_number(value):
    """Le champ « Numéro de navette » ne contient que le numéro ('3'), mais
    on tolère une saisie du type 'Navette 3' pour ne pas afficher
    « NAVETTE NAVETTE 3 ». Renvoie '' si rien n'est renseigné."""
    number = (value or "").strip()
    if number.lower().startswith("navette"):
        number = number[len("navette"):].strip()
    return number


def register_jinja_filters(app):
    app.jinja_env.filters["fmt_time"] = fmt_time
    app.jinja_env.filters["fmt_date_short"] = fmt_date_short
    app.jinja_env.filters["fmt_date_long"] = fmt_date_long
    app.jinja_env.filters["fmt_date_full"] = fmt_date_full
    app.jinja_env.filters["day_label"] = day_label
