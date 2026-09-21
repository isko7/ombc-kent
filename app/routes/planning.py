"""
Écran Planning (vue calendrier hebdomadaire des missions) + flux
iCalendar public pour l'abonnement depuis Calendrier iPhone / Google
Agenda (voir app/ical_service.py).
"""
import secrets
from datetime import date, timedelta

from flask import Blueprint, render_template, request, url_for, abort, Response

from app import repo
from app.config import CALENDAR_FEED_TOKEN
from app.ical_service import build_ics, local_to_utc
from app.utils import driver_color, fmt_hours_minutes, legs_time_summary, service_time_range

bp = Blueprint("planning", __name__, url_prefix="/planning")

# Fenêtre du flux .ics : assez large pour qu'un abonnement affiche les
# missions passées récentes et les mois à venir, assez bornée pour rester
# rapide à générer et à parser côté client.
FEED_PAST_DAYS = 14
FEED_FUTURE_DAYS = 180


def _build_event(mission, drivers_by_id):
    legs = mission.get("legs") or []
    # service_time_range() normalise ':' / 'h' et ignore les points de
    # contrôle sans horaire exploitable (même règle que la liste des OM).
    start_time, end_time = service_time_range(legs)
    vehicles = []
    for leg in legs:
        plate = leg.get("vehicle_plate")
        if plate and plate not in vehicles:
            vehicles.append(plate)

    driver = drivers_by_id.get(mission["driver_id"])
    driver_name = f"{mission['driver_last_name']} {mission['driver_first_name']}"
    event = {
        "mission_id": mission["id"],
        "reference": mission["reference"],
        "title": mission.get("mission_name") or mission["reference"],
        "driver_id": mission["driver_id"],
        "driver_name": driver_name,
        "color": driver_color(driver or {"id": mission["driver_id"]}),
        "vehicle": " + ".join(vehicles),
        "status": mission["status"],
        "date": mission["mission_date"],
        "url": url_for("missions.detail_mission", mission_id=mission["id"]),
    }
    if start_time:
        event["all_day"] = False
        event["start_time"] = start_time
        event["end_time"] = end_time
        # Strictement < : à heures égales (trajet ponctuel), on affiche une
        # durée minimale plutôt que d'étendre le bloc jusqu'à minuit.
        event["crosses_midnight"] = end_time < start_time
        summary = legs_time_summary(legs)
        event["amplitude"] = fmt_hours_minutes(summary["amplitude"]) if summary else None
    else:
        event["all_day"] = True
    return event


@bp.route("/")
def calendar_view():
    raw_date = request.args.get("date")
    try:
        ref_date = date.fromisoformat(raw_date) if raw_date else date.today()
    except ValueError:
        ref_date = date.today()
    monday = ref_date - timedelta(days=ref_date.weekday())
    week_days = [monday + timedelta(days=i) for i in range(7)]
    driver_id = request.args.get("driver_id", type=int)

    missions = repo.list_missions_for_planning(
        monday.isoformat(), week_days[-1].isoformat(), driver_id=driver_id
    )
    drivers = repo.list_drivers()
    drivers_by_id = {d["id"]: d for d in drivers}
    events = [_build_event(m, drivers_by_id) for m in missions]

    # Vue agenda (mobile, rendue côté serveur — pas de JS requis) : mêmes
    # événements, groupés par jour et triés (toute la journée en tête).
    events_by_day = {d.isoformat(): [] for d in week_days}
    for ev in events:
        events_by_day.setdefault(ev["date"], []).append(ev)
    for day_events in events_by_day.values():
        day_events.sort(key=lambda e: ("" if e["all_day"] else e["start_time"]))

    feed_url = (
        url_for("planning.calendar_feed", token=CALENDAR_FEED_TOKEN, _external=True)
        if CALENDAR_FEED_TOKEN else None
    )

    return render_template(
        "planning/calendar.html",
        events=events,
        events_by_day=events_by_day,
        week_days=week_days,
        monday=monday.isoformat(),
        week_number=monday.isocalendar()[1],
        prev_date=(monday - timedelta(days=7)).isoformat(),
        next_date=(monday + timedelta(days=7)).isoformat(),
        today_date=date.today().isoformat(),
        drivers=drivers,
        filters={"driver_id": driver_id},
        feed_enabled=bool(CALENDAR_FEED_TOKEN),
        feed_url=feed_url,
        suggested_token=None if CALENDAR_FEED_TOKEN else secrets.token_urlsafe(24),
    )


def _ics_description(mission, event):
    parts = [f"Chauffeur : {event['driver_name']}"]
    if event.get("vehicle"):
        parts.append(f"Véhicule : {event['vehicle']}")
    if mission.get("client_name"):
        parts.append(f"Client : {mission['client_name']}")
    if mission.get("motif"):
        parts.append(f"Motif : {mission['motif']}")
    parts.append(f"Référence : {mission['reference']}")
    return "\n".join(parts)


@bp.route("/calendrier.ics")
def calendar_feed():
    """Flux iCalendar public : GET /planning/calendrier.ics?token=...
    [&driver_id=...]. Comme /admin/init, 404 si CALENDAR_FEED_TOKEN n'est
    pas configuré (pas d'indice qu'une route existe), 403 si le jeton ne
    correspond pas."""
    if not CALENDAR_FEED_TOKEN:
        abort(404)
    if request.args.get("token") != CALENDAR_FEED_TOKEN:
        abort(403)

    driver_id = request.args.get("driver_id", type=int)
    today = date.today()
    date_from = (today - timedelta(days=FEED_PAST_DAYS)).isoformat()
    date_to = (today + timedelta(days=FEED_FUTURE_DAYS)).isoformat()
    missions = repo.list_missions_for_planning(date_from, date_to, driver_id=driver_id)
    drivers_by_id = {d["id"]: d for d in repo.list_drivers()}

    calendar_name = "Planning Transports KENT"
    if driver_id and driver_id in drivers_by_id:
        d = drivers_by_id[driver_id]
        calendar_name = f"Planning {d['last_name']} {d['first_name']} — Transports KENT"

    ics_events = []
    for mission in missions:
        event = _build_event(mission, drivers_by_id)
        ics_event = {
            "mission_id": event["mission_id"],
            "title": f"{event['title']} — {event['driver_name']}",
            "url": url_for("missions.detail_mission", mission_id=event["mission_id"], _external=True),
            "status": event["status"],
            "description": _ics_description(mission, event),
        }
        if event["all_day"]:
            ics_event["all_day"] = True
            ics_event["date"] = event["date"]
        else:
            ics_event["start_utc"] = local_to_utc(event["date"], event["start_time"])
            end_date = event["date"]
            if event["crosses_midnight"]:
                end_date = (date.fromisoformat(event["date"]) + timedelta(days=1)).isoformat()
            ics_event["end_utc"] = local_to_utc(end_date, event["end_time"])
        ics_events.append(ics_event)

    body = build_ics(ics_events, calendar_name=calendar_name)
    return Response(
        body, mimetype="text/calendar",
        headers={"Content-Disposition": 'inline; filename="planning-kent.ics"'},
    )
