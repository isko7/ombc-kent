"""Petits utilitaires de formatage (dates/heures en français)."""
from datetime import date, datetime

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


def register_jinja_filters(app):
    app.jinja_env.filters["fmt_time"] = fmt_time
    app.jinja_env.filters["fmt_date_short"] = fmt_date_short
    app.jinja_env.filters["fmt_date_long"] = fmt_date_long
    app.jinja_env.filters["day_label"] = day_label
