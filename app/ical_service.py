"""
Génération du flux iCalendar (RFC 5545) du planning — abonnement
Calendrier iPhone / Google Agenda.

Aucune dépendance externe (ni `icalendar`, ni `pytz`/`zoneinfo` : la
machine de dev n'a pas forcément la base de fuseaux IANA installée, cf.
`app/utils.py` qui gère déjà les dates/heures « à la main »). Le décalage
Europe/Paris est calculé directement à partir de la règle DST de l'Union
européenne (dernier dimanche de mars -> dernier dimanche d'octobre).
"""
from datetime import date, datetime, timedelta


def _last_sunday(year, month):
    next_month = date(year + 1, 1, 1) if month == 12 else date(year, month + 1, 1)
    last_day = next_month - timedelta(days=1)
    return last_day - timedelta(days=(last_day.weekday() - 6) % 7)


def paris_utc_offset_hours(d):
    """+2 (CEST, heure d'été) entre le dernier dimanche de mars et le
    dernier dimanche d'octobre, +1 (CET, heure d'hiver) sinon."""
    dst_start = _last_sunday(d.year, 3)
    dst_end = _last_sunday(d.year, 10)
    return 2 if dst_start <= d < dst_end else 1


def local_to_utc(mission_date, hhmm):
    """'2026-09-24' + '05:30' (heure de Paris) -> datetime UTC naïf."""
    d = date.fromisoformat(mission_date[:10])
    h, m = (int(p) for p in hhmm.split(":")[:2])
    naive = datetime(d.year, d.month, d.day, h, m)
    return naive - timedelta(hours=paris_utc_offset_hours(d))


def _escape(text):
    """Échappement RFC 5545 des valeurs TEXT (SUMMARY/DESCRIPTION/LOCATION)."""
    text = str(text)
    text = text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,")
    return text.replace("\r\n", "\\n").replace("\n", "\\n")


def _fold(line):
    """Replie une ligne dépassant 75 octets (RFC 5545 §3.1) : chaque ligne
    de continuation commence par un espace. Ne coupe jamais un caractère
    UTF-8 multi-octets."""
    data = line.encode("utf-8")
    if len(data) <= 75:
        return line
    chunks, start, limit = [], 0, 75
    while start < len(data):
        end = min(start + limit, len(data))
        while end < len(data) and (data[end] & 0xC0) == 0x80:
            end -= 1
        chunks.append(data[start:end].decode("utf-8"))
        start, limit = end, 74
    return "\r\n ".join(chunks)


def build_ics(events, calendar_name="Planning"):
    """`events` : liste de dicts avec soit ('all_day': True, 'date':
    'YYYY-MM-DD'), soit ('start_utc'/'end_utc': datetime naïfs UTC), plus
    'mission_id', 'title', 'url', et optionnellement 'location',
    'description', 'status' ('brouillon' -> TENTATIVE)."""
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Transports KENT//Planning//FR",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        _fold(f"X-WR-CALNAME:{_escape(calendar_name)}"),
        "X-WR-TIMEZONE:Europe/Paris",
        "REFRESH-INTERVAL;VALUE=DURATION:PT1H",
        "X-PUBLISHED-TTL:PT1H",
    ]
    for ev in events:
        lines.append("BEGIN:VEVENT")
        lines.append(f"UID:kent-mission-{ev['mission_id']}@transports-kent")
        lines.append(f"DTSTAMP:{now}")
        if ev.get("all_day"):
            d = date.fromisoformat(ev["date"])
            lines.append(f"DTSTART;VALUE=DATE:{d.strftime('%Y%m%d')}")
            lines.append(f"DTEND;VALUE=DATE:{(d + timedelta(days=1)).strftime('%Y%m%d')}")
        else:
            lines.append(f"DTSTART:{ev['start_utc'].strftime('%Y%m%dT%H%M%SZ')}")
            lines.append(f"DTEND:{ev['end_utc'].strftime('%Y%m%dT%H%M%SZ')}")
        lines.append(_fold(f"SUMMARY:{_escape(ev['title'])}"))
        if ev.get("location"):
            lines.append(_fold(f"LOCATION:{_escape(ev['location'])}"))
        if ev.get("description"):
            lines.append(_fold(f"DESCRIPTION:{_escape(ev['description'])}"))
        if ev.get("url"):
            lines.append(_fold(f"URL:{ev['url']}"))
        lines.append(f"STATUS:{'TENTATIVE' if ev.get('status') == 'brouillon' else 'CONFIRMED'}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    return "\r\n".join(lines) + "\r\n"
