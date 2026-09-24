"""Petits utilitaires de formatage (dates/heures en français)."""
import re
import unicodedata
from datetime import date, datetime, timedelta

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


def now_paris():
    """Date et heure courantes à Paris. Le serveur tourne en UTC (Vercel) :
    sans correction, une mission qui se termine à 23h50 serait considérée
    comme passée dès 21h50 en France (voir la liste des OM, onglet
    « Missions passées »)."""
    # Import local : ical_service ne dépend de rien, mais utils est importé
    # très tôt (filtres Jinja) — on évite d'y ajouter une dépendance au
    # chargement.
    from app.ical_service import paris_utc_offset_hours
    utc_now = datetime.utcnow()
    return utc_now + timedelta(hours=paris_utc_offset_hours(utc_now.date()))


def fmt_time(hhmm):
    """'11:00' -> '11h00'. Laisse passer une chaîne déjà au format 11h00."""
    if not hhmm:
        return ""
    return hhmm.replace(":", "h")


_TIME_PATTERN = re.compile(r"^(\d{1,2})\s*[:hH]\s*(\d{1,2})$")
_STRICT_TIME_PATTERN = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def normalize_time(value):
    """'11h00', '11:00', '9h5' -> '11:00' (HH:MM zero-paddé). Le champ de
    trajet (formulaire OM) est un champ texte libre : rien n'empêche de
    taper le séparateur 'h' qu'on voit partout ailleurs dans l'appli
    (fmt_time) plutôt que ':'. Une valeur qui ne ressemble pas à une heure
    (vide, texte libre type note du chauffeur) est renvoyée telle quelle,
    sans y toucher — seul le séparateur/zéro-padding est corrigé."""
    if not value:
        return value
    m = _TIME_PATTERN.match(value.strip())
    if not m:
        return value
    h, mn = int(m.group(1)), int(m.group(2))
    if not (0 <= h <= 23 and 0 <= mn <= 59):
        return value
    return f"{h:02d}:{mn:02d}"


def is_valid_time(value):
    """Vrai si `value` est strictement au format HH:MM (00-23:00-59)."""
    return bool(value) and bool(_STRICT_TIME_PATTERN.match(value))


def service_time_range(legs):
    """Heure de prise de service / fin de service d'une mission : première
    et dernière heure valide parmi ses trajets, dans l'ordre. Ignore les
    points de contrôle sans horaire exploitable (ex. « Prise de service »
    laissée vide, remplie à la main par le chauffeur). (None, None) si
    aucun trajet horodaté."""
    timed = []
    for leg in legs or []:
        s, e = normalize_time(leg.get("start_time")), normalize_time(leg.get("end_time"))
        if is_valid_time(s) and is_valid_time(e):
            timed.append((s, e))
    if not timed:
        return None, None
    return timed[0][0], timed[-1][1]


def _to_minutes(hhmm):
    h, m = hhmm.split(":")
    return int(h) * 60 + int(m)


def legs_time_summary(legs):
    """Amplitude / temps de conduite / temps de pause d'une mission, à
    partir de ses trajets (même calcul que le récap en direct du
    formulaire OM, mission_form.js) :
    - amplitude : prise de service -> fin de service (service_time_range).
    - conduite  : somme des trajets avec un véhicule réel affecté (hors
      relais et points de contrôle).
    - pause     : amplitude - conduite, c'est-à-dire le reste du temps de
      service qui n'est pas passé à conduire (attente, relais...) — ce
      n'est pas une saisie séparée, juste le complément.
    None si pas assez d'horaires pour calculer l'amplitude. Le modulo 1440
    (minutes/jour) gère les missions de nuit qui passent minuit (ex. prise de
    service 19h00, fin de service 02h30 -> 7h30 d'amplitude, pas -16h30)."""
    start, end = service_time_range(legs)
    if start is None:
        return None
    amplitude = (_to_minutes(end) - _to_minutes(start)) % 1440
    driving = 0
    for leg in legs or []:
        if leg.get("is_relay") or leg.get("is_checkpoint") or not leg.get("vehicle_id"):
            continue
        s, e = normalize_time(leg.get("start_time")), normalize_time(leg.get("end_time"))
        if is_valid_time(s) and is_valid_time(e):
            driving += (_to_minutes(e) - _to_minutes(s)) % 1440
    return {"amplitude": amplitude, "driving": driving, "pause": max(0, amplitude - driving)}


def legs_distance_summary(legs):
    """Distances d'une mission, en mètres, à partir des distances estimées
    de ses trajets (mission_legs.distance_m) :
    - total     : dépôt -> dépôt, c'est-à-dire la somme de tous les trajets.
    - à vide    : les trajets dont une extrémité est le dépôt (aller au
      premier point, retour du dernier point) — personne à bord.
    - transport : le reste, du premier au dernier point de la prestation.

    Le sens se lit dans le libellé (« A → B ») : un côté qui désigne le
    dépôt (is_depot, accents et casse indifférents) marque un trajet à
    vide. Les trajets sans distance estimée (point de contrôle, pause,
    libellé libre) sont ignorés. None si aucun trajet n'est estimé — il n'y
    a alors rien à afficher, et surtout pas « 0 km »."""
    total = empty = 0
    known = False
    for leg in legs or []:
        meters = leg.get("distance_m")
        if meters is None:
            continue
        known = True
        total += meters
        sides = (leg.get("label") or "").split(" → ")
        if len(sides) == 2 and any(is_depot(side) for side in sides):
            empty += meters
    if not known:
        return None
    return {"total": total, "empty": empty, "transport": total - empty}


def fmt_km(meters):
    """125400 -> '125 km'. None/manquant -> '—'. L'espace est insécable :
    un nombre ne doit pas se retrouver séparé de son unité en fin de ligne."""
    if meters is None:
        return "—"
    return f"{round(meters / 1000)} km"


def fmt_hours_minutes(minutes):
    """125 -> '2h05'. None/manquant -> '—' (même format que
    formatHoursMinutes en JS, mission_form.js)."""
    if minutes is None:
        return "—"
    h, m = divmod(int(round(minutes)), 60)
    return f"{h}h{m:02d}"


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


def fmt_day_header(value):
    """date ou 'YYYY-MM-DD' -> 'Lundi 14 septembre' (en-tête de jour du
    planning hebdomadaire)."""
    d = parse_iso_date(value)
    return f"{WEEKDAYS_FR[d.weekday()]} {d.day} {MONTHS_FR[d.month - 1]}" if d else ""


def _fold(text):
    """Minuscules sans accents, pour comparer « Dépôt » et « Depot »."""
    decomposed = unicodedata.normalize("NFD", (text or "").strip().lower())
    return "".join(c for c in decomposed if unicodedata.category(c) != "Mn")


def is_depot(text):
    """Vrai si le libellé désigne le dépôt, quelle que soit la casse ou la
    présence des accents (la génération automatique écrit « Dépôt KENT »,
    mais une saisie manuelle peut donner « Depot KENT »)."""
    return _fold(text) == _fold(DEPOT_LABEL)


def fmt_week_range(monday):
    """date du lundi -> '14 – 20 septembre 2026' (gère mois/année différents
    entre le lundi et le dimanche de la même semaine, ex. 'décembre 2026'
    -> 'janvier 2027')."""
    d = parse_iso_date(monday)
    if not d:
        return ""
    sunday = d + timedelta(days=6)
    if d.year != sunday.year:
        left = f"{d.day} {MONTHS_FR[d.month - 1]} {d.year}"
    elif d.month != sunday.month:
        left = f"{d.day} {MONTHS_FR[d.month - 1]}"
    else:
        left = f"{d.day}"
    right = f"{sunday.day} {MONTHS_FR[sunday.month - 1]} {sunday.year}"
    return f"{left} – {right}"


# Palette par défaut assignée aux chauffeurs sans couleur personnalisée
# (répartition round-robin sur l'id) : couleurs distinctes et lisibles en
# texte blanc, pensées pour un calendrier (pas trop pâles, pas trop criardes).
DRIVER_COLOR_PALETTE = [
    "#1d63d8", "#d6293a", "#1e8a5f", "#b8590a", "#6e3fbf",
    "#0f9aa8", "#c2185b", "#5d7a1f", "#a8471f", "#3457b2",
]


def driver_color(driver):
    """Couleur d'affichage d'un chauffeur : celle choisie sur sa fiche, ou
    une couleur de la palette par défaut assignée à partir de son id (stable
    tant que le chauffeur n'est pas supprimé/recréé)."""
    if not driver:
        return DRIVER_COLOR_PALETTE[0]
    color = (driver.get("color") or "").strip()
    if color:
        return color
    return DRIVER_COLOR_PALETTE[(driver.get("id") or 0) % len(DRIVER_COLOR_PALETTE)]


def balance_passenger_counts(stops):
    """Équilibre le nombre de voyageurs des arrêts du Billet Collectif.

    Quand tout le monde est ramassé à plusieurs endroits puis déposé au même
    point (N prises en charge -> 1 dépose), la dépose porte forcément le
    total des prises en charge. Symétriquement, un ramassage unique suivi de
    plusieurs déposes porte le total des déposes.

    L'arrêt « agrégé » est donc recalculé, jamais saisi. Les autres cas
    (1 <-> 1, ou N <-> N) restent ambigus : on n'y touche pas.

    Modifie `stops` sur place et renvoie l'index recalculé, ou None.
    """
    pickups = [s for s in stops if s.get("stop_type") == "prise_en_charge"]
    dropoffs = [s for s in stops if s.get("stop_type") == "depose"]

    def total(group):
        return sum(int(s.get("passenger_count") or 1) for s in group)

    if len(dropoffs) == 1 and len(pickups) >= 2:
        aggregated = dropoffs[0]
        aggregated["passenger_count"] = total(pickups)
    elif len(pickups) == 1 and len(dropoffs) >= 2:
        aggregated = pickups[0]
        aggregated["passenger_count"] = total(dropoffs)
    else:
        return None
    return stops.index(aggregated)


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
    app.jinja_env.filters["fmt_day_header"] = fmt_day_header
    app.jinja_env.filters["day_label"] = day_label
    app.jinja_env.filters["driver_color"] = driver_color
    app.jinja_env.filters["fmt_week_range"] = fmt_week_range
    app.jinja_env.filters["fmt_hours_minutes"] = fmt_hours_minutes
    app.jinja_env.filters["fmt_km"] = fmt_km
    app.jinja_env.filters["shuttle_number"] = shuttle_number
