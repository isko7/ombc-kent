from datetime import date, timedelta
from pathlib import Path

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, Response, abort, jsonify
)
from werkzeug.utils import secure_filename

from app import repo
from app.config import COMPANY, RANDSTAD_EMAIL, GOOGLE_MAPS_API_KEY
from app.pdf_service import (
    generate_mission_pdf, extract_pdf_pages, PdfGenerationError,
    POSITION_BEFORE_OM, POSITION_AFTER_OM, POSITION_AFTER_BC,
)
from app.email_service import send_mission_email, send_bulk_email, EmailError
from app.routing import estimate_route, format_duration, add_minutes, RoutingError
from app.routes.settings import get_address_search_provider
from app.utils import (
    fmt_date_full, fmt_date_long, fmt_date_short, fmt_time, legs_time_summary,
    normalize_time, service_time_range, shuttle_number,
)

bp = Blueprint("missions", __name__, url_prefix="/missions")

ATTACHMENT_POSITIONS = [
    (POSITION_BEFORE_OM, "Avant l'Ordre de mission"),
    (POSITION_AFTER_OM, "Après l'OM, avant le BC (page 2 — recommandé pour la feuille de référence)"),
    (POSITION_AFTER_BC, "Après le Billet collectif"),
]

ALLOWED_ATTACHMENT_EXT = {".pdf", ".png", ".jpg", ".jpeg"}

PER_PAGE = 50


def _at(lst, i, default=""):
    return lst[i] if i < len(lst) else default


def _parse_legs(form):
    # Indexation "sûre" plutôt que zip() : si un champ optionnel est absent
    # du formulaire pour certaines lignes, on ne désaligne pas les autres.
    starts = form.getlist("leg_start_time[]")
    ends = form.getlist("leg_end_time[]")
    vehicle_ids = form.getlist("leg_vehicle_id[]")
    labels = form.getlist("leg_label[]")
    relay_drivers = form.getlist("leg_relay_driver_id[]")
    n = max(len(starts), len(ends), len(vehicle_ids), len(labels))
    legs = []
    for i in range(n):
        s, e, v, l = _at(starts, i).strip(), _at(ends, i).strip(), _at(vehicle_ids, i), _at(labels, i).strip()
        if not s and not e and not l:
            continue
        # Le champ est du texte libre : normalise "11h00" saisi par réflexe
        # (c'est le format affiché partout ailleurs) vers "11:00".
        s, e = normalize_time(s), normalize_time(e)
        is_relay = v == "relais"
        rd = _at(relay_drivers, i)
        # Point de contrôle : début = fin, ou une prise/fin de service (dont
        # les heures sont laissées vides, remplies à la main par le chauffeur).
        is_service = l.lower().startswith(("prise de service", "fin de service"))
        legs.append({
            "start_time": s,
            "end_time": e,
            "vehicle_id": int(v) if (v and v.isdigit()) else None,
            "label": l,
            "is_checkpoint": ((bool(s) and s == e) or is_service) and not is_relay,
            "is_relay": is_relay,
            "relay_driver_id": int(rd) if (is_relay and rd and rd.isdigit()) else None,
        })
    return legs


def _parse_stops(form):
    types = form.getlist("stop_type[]")
    dates = form.getlist("stop_date[]")
    times = form.getlist("stop_time[]")
    addresses = form.getlist("stop_address[]")
    cities = form.getlist("stop_city[]")
    counts = form.getlist("stop_passenger_count[]")
    names = form.getlist("stop_passenger_name[]")
    phones = form.getlist("stop_passenger_phone[]")
    refs = form.getlist("stop_booking_ref[]")
    n = len(addresses)
    stops = []
    for i in range(n):
        a = _at(addresses, i).strip()
        if not a:
            continue
        cnt = _at(counts, i).strip()
        stops.append({
            "stop_type": _at(types, i) if _at(types, i) in ("prise_en_charge", "depose") else "depose",
            "stop_date": _at(dates, i) or None,
            "stop_time": _at(times, i).strip(),
            "address": a,
            "city": _at(cities, i).strip() or None,
            "passenger_count": int(cnt) if cnt.isdigit() else 1,
            "passenger_name": _at(names, i).strip() or None,
            "passenger_phone": _at(phones, i).strip() or None,
            "booking_ref": _at(refs, i).strip() or None,
        })
    return stops


def _mission_form_to_data(form):
    data = {
        "driver_id": int(form["driver_id"]) if form.get("driver_id") else None,
        "mission_date": form.get("mission_date") or None,
        "mission_name": form.get("mission_name", "").strip() or None,
        "shuttle_label": form.get("shuttle_label", "").strip() or None,
        "motif": form.get("motif", "").strip() or "Transport Occasionnel",
        "remarks": form.get("remarks", "").strip() or None,
        "client_id": int(form["client_id"]) if form.get("client_id") else None,
        "emission_date": form.get("emission_date") or None,
        "price": form.get("price", "").strip() or None,
        "status": form.get("status") or "brouillon",
        "om_template_id": int(form["om_template_id"]) if form.get("om_template_id") else None,
        "bc_template_id": int(form["bc_template_id"]) if form.get("bc_template_id") else None,
    }
    # Les arrêts (BC) alimentent aussi par défaut les dates des trajets (OM)
    # via mission_date déjà fourni ; on complète stop_date manquant.
    stops = _parse_stops(form)
    for s in stops:
        s["stop_date"] = s["stop_date"] or data["mission_date"]
    data["legs"] = _parse_legs(form)
    data["stops"] = stops
    return data


def _form_context(mission=None):
    return {
        "drivers": repo.list_drivers(include_inactive=False),
        "vehicles": repo.list_vehicles(include_inactive=False),
        "clients": repo.list_clients(pinned_first=True),
        "om_templates": repo.list_templates("OM"),
        "bc_templates": repo.list_templates("BC"),
        "mission": mission,
        "google_maps_api_key": GOOGLE_MAPS_API_KEY,
        "address_search_provider": get_address_search_provider(),
        "depot_address": f"{COMPANY['address']}, {COMPANY['postal_code']} {COMPANY['city']}",
    }


@bp.route("/")
def list_missions_view():
    driver_id = request.args.get("driver_id", type=int)
    date_from = request.args.get("date_from") or None
    date_to = request.args.get("date_to") or None
    status = request.args.get("status") or None
    name = request.args.get("name", "").strip() or None
    tab = "past" if request.args.get("tab") == "past" else "current"

    # L'onglet pose une borne de date automatique, combinée (ET) avec les
    # bornes saisies dans les filtres : c'est la plus restrictive qui gagne.
    today = date.today().isoformat()
    if tab == "past":
        yesterday = (date.today() - timedelta(days=1)).isoformat()
        eff_from, eff_to = date_from, min(date_to, yesterday) if date_to else yesterday
    else:
        eff_from, eff_to = (max(date_from, today) if date_from else today), date_to

    criteria = dict(driver_id=driver_id, date_from=eff_from, date_to=eff_to,
                    status=status, name=name)
    total = repo.count_missions(**criteria)
    total_pages = max(1, -(-total // PER_PAGE))  # division entière arrondie au supérieur
    page = min(max(request.args.get("page", type=int) or 1, 1), total_pages)

    missions = repo.list_missions(
        **criteria,
        ascending=(tab == "current"),  # à venir : le plus proche d'abord
        limit=PER_PAGE, offset=(page - 1) * PER_PAGE,
    )
    repo.attach_legs(missions)
    for m in missions:
        m["service_start"], m["service_end"] = service_time_range(m["legs"])
        summary = legs_time_summary(m["legs"])
        m["amplitude_minutes"] = summary["amplitude"] if summary else None
    return render_template(
        "missions/list.html", missions=missions, drivers=repo.list_drivers(), tab=tab,
        total=total, page=page, total_pages=total_pages,
        filters={"driver_id": driver_id, "date_from": date_from, "date_to": date_to,
                 "status": status, "name": name},
    )


@bp.route("/estimer-duree", methods=["POST"])
def estimate_leg_duration():
    """Estimation de la durée d'une ligne de trajet (bouton « Estimer »
    du formulaire). Appelé en fetch, répond en JSON. La clé TomTom reste
    côté serveur."""
    origin = request.form.get("from", "").strip()
    destination = request.form.get("to", "").strip()
    if not origin or not destination:
        return jsonify({"ok": False, "error": "Le libellé doit être de la forme « départ → arrivée »."}), 400
    # Heure de début prioritaire ; à défaut, heure de fin (arriver à l'heure).
    start_time = request.form.get("start_time", "").strip() or None
    end_time = request.form.get("end_time", "").strip() or None
    try:
        result = estimate_route(
            origin, destination,
            mission_date=request.form.get("mission_date") or None,
            start_time=start_time, end_time=end_time,
        )
    except RoutingError as e:
        return jsonify({"ok": False, "error": str(e)}), 502

    return jsonify({
        "ok": True,
        "duration": format_duration(result["duration_s"]),
        "km": round(result["distance_m"] / 1000),
        "traffic_min": round(result["traffic_delay_s"] / 60),
        "with_traffic_at": result["departure"],
        # Heure estimée, affichée seulement — les champs ne sont pas modifiés.
        "arrival_time": add_minutes(start_time, result["duration_s"]) if start_time else None,
        "departure_time": add_minutes(end_time, -result["duration_s"]) if not start_time and end_time else None,
    })


@bp.route("/nouveau", methods=["GET", "POST"])
def new_mission():
    if request.method == "POST":
        data = _mission_form_to_data(request.form)
        if not data["driver_id"] or not data["mission_date"]:
            flash("Chauffeur et date de mission sont obligatoires.", "error")
            return render_template("missions/form.html", is_new=True, **_form_context(data))
        mission_id = repo.create_mission(data)
        flash("Ordre de mission créé.", "success")
        return redirect(url_for("missions.detail_mission", mission_id=mission_id))
    return render_template("missions/form.html", is_new=True, **_form_context({
        "status": "brouillon", "motif": "Transport Occasionnel",
        "driver_id": None, "client_id": None, "om_template_id": None, "bc_template_id": None,
        "mission_date": "", "mission_name": "", "emission_date": date.today().isoformat(),
        "shuttle_label": "", "price": "", "remarks": "",
        "legs": [], "stops": [],
    }))


def _billing_summary(mission):
    """Récapitulatif à copier-coller pour la facturation (affiché sur la
    fiche mission, jamais dans le PDF) :

        NAVETTE 3 - Aller - 24/08/2026 03h30

        Prise en charge : Illiers-Combray, 1 rue A - 2 pax
        Dépose : Fleury-les-Aubrais, PK Simplon - 6 pax

    Le sens est déduit des arrêts : une dépose unique = aller (on ramasse
    puis on dépose tout le monde au même endroit), une prise en charge
    unique = retour."""
    stops = mission.get("stops") or []

    n_pickup = sum(1 for s in stops if s["stop_type"] == "prise_en_charge")
    n_dropoff = len(stops) - n_pickup
    if n_pickup == 1 and n_dropoff > 1:
        direction = "Retour"
    elif n_dropoff == 1 and n_pickup > 1:
        direction = "Aller"
    else:
        direction = "Aller" if n_pickup >= n_dropoff else "Retour"

    number = shuttle_number(mission.get("shuttle_label"))
    # Heure du 1er arrêt du Billet Collectif (pas celle de la prise de service).
    start = stops[0]["stop_time"] if stops else ""
    header = " - ".join([
        f"NAVETTE {number or 'X'}",
        direction,
        f"{fmt_date_long(mission['mission_date'])} {fmt_time(start)}".strip(),
    ])

    lines = []
    for s in stops:
        place = ", ".join(p for p in [(s.get("city") or "").strip(),
                                      (s.get("address") or "").strip()] if p)
        if not place:
            continue
        label = "Prise en charge" if s["stop_type"] == "prise_en_charge" else "Dépose"
        lines.append(f"{label} : {place} - {s.get('passenger_count') or 1} pax")
    return header + "\n\n" + "\n".join(lines) if lines else header


@bp.route("/<int:mission_id>")
def detail_mission(mission_id):
    mission = repo.get_mission(mission_id)
    if not mission:
        abort(404)
    emails = repo.list_email_log(mission_id)
    return render_template("missions/detail.html", mission=mission, emails=emails,
                            positions=ATTACHMENT_POSITIONS,
                            billing_summary=_billing_summary(mission),
                            legs_summary=legs_time_summary(mission["legs"]))


@bp.route("/<int:mission_id>/modifier", methods=["GET", "POST"])
def edit_mission(mission_id):
    existing = repo.get_mission(mission_id)
    if not existing:
        abort(404)
    if request.method == "POST":
        data = _mission_form_to_data(request.form)
        if not data["driver_id"] or not data["mission_date"]:
            flash("Chauffeur et date de mission sont obligatoires.", "error")
            data["id"] = mission_id
            return render_template("missions/form.html", is_new=False, mission_id=mission_id,
                                    **_form_context(data))
        repo.update_mission(mission_id, data)
        flash("Ordre de mission mis à jour.", "success")
        return redirect(url_for("missions.detail_mission", mission_id=mission_id))
    return render_template("missions/form.html", is_new=False, mission_id=mission_id,
                            **_form_context(existing))


@bp.route("/<int:mission_id>/supprimer", methods=["POST"])
def delete_mission(mission_id):
    repo.delete_mission(mission_id)
    flash("Ordre de mission supprimé.", "success")
    return redirect(url_for("missions.list_missions_view"))


@bp.route("/<int:mission_id>/dupliquer", methods=["POST"])
def duplicate_mission(mission_id):
    new_id = repo.duplicate_mission(mission_id)
    if not new_id:
        abort(404)
    flash("Ordre de mission dupliqué — pensez à ajuster la date.", "success")
    return redirect(url_for("missions.edit_mission", mission_id=new_id))


@bp.route("/<int:mission_id>/retour", methods=["POST"])
def create_return_mission(mission_id):
    new_id = repo.create_return_mission(mission_id)
    if not new_id:
        abort(404)
    flash("Trajet retour créé (arrêts et trajets inversés) — vérifiez date et horaires.", "success")
    return redirect(url_for("missions.edit_mission", mission_id=new_id))


@bp.route("/<int:mission_id>/pdf")
def mission_pdf(mission_id):
    try:
        pdf_bytes, filename = generate_mission_pdf(mission_id)
    except PdfGenerationError as e:
        flash(str(e), "error")
        return redirect(url_for("missions.detail_mission", mission_id=mission_id))
    disposition = "inline" if request.args.get("inline") else "attachment"
    return Response(
        pdf_bytes, mimetype="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


@bp.route("/<int:mission_id>/pieces-jointes", methods=["POST"])
def upload_attachment(mission_id):
    mission = repo.get_mission(mission_id)
    if not mission:
        abort(404)
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Aucun fichier sélectionné.", "error")
        return redirect(url_for("missions.detail_mission", mission_id=mission_id))
    ext = Path(file.filename).suffix.lower()
    if ext not in ALLOWED_ATTACHMENT_EXT:
        flash("Formats acceptés : PDF, PNG, JPG.", "error")
        return redirect(url_for("missions.detail_mission", mission_id=mission_id))
    content = file.read()
    if not content:
        flash("Fichier vide.", "error")
        return redirect(url_for("missions.detail_mission", mission_id=mission_id))

    filename = secure_filename(file.filename)
    pages_spec = request.form.get("pages", "").strip()
    if ext == ".pdf" and pages_spec:
        try:
            content = extract_pdf_pages(content, pages_spec)
        except PdfGenerationError as e:
            flash(f"Sélection de pages invalide : {e}", "error")
            return redirect(url_for("missions.detail_mission", mission_id=mission_id))
        filename = f"{Path(filename).stem}_p{pages_spec.replace(',', '+')}.pdf"

    insert_after_page = request.form.get("insert_after_page", type=int)
    if insert_after_page is None:
        insert_after_page = POSITION_AFTER_OM
    repo.add_attachment(mission_id, filename, content, file.mimetype, insert_after_page)
    flash("Pièce jointe ajoutée.", "success")
    return redirect(url_for("missions.detail_mission", mission_id=mission_id))


@bp.route("/<int:mission_id>/pieces-jointes/<int:attachment_id>/supprimer", methods=["POST"])
def delete_attachment(mission_id, attachment_id):
    att = repo.get_attachment(attachment_id)
    if att and att["mission_id"] == mission_id:
        repo.delete_attachment(attachment_id)
        flash("Pièce jointe supprimée.", "success")
    return redirect(url_for("missions.detail_mission", mission_id=mission_id))


@bp.route("/<int:mission_id>/email", methods=["GET", "POST"])
def email_mission(mission_id):
    mission = repo.get_mission(mission_id)
    if not mission:
        abort(404)
    driver = mission["driver"]

    if request.method == "POST":
        to_list = [e.strip() for e in request.form.get("to", "").split(",") if e.strip()]
        cc_raw = request.form.get("cc", "")
        cc_list = [e.strip() for e in cc_raw.split(",") if e.strip()]
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "")
        if not to_list or not subject:
            flash("Au moins un destinataire et un objet sont requis.", "error")
            return redirect(url_for("missions.email_mission", mission_id=mission_id))
        try:
            pdf_bytes, filename = generate_mission_pdf(mission_id)
            send_mission_email(mission_id, to_list, cc_list, subject, body, pdf_bytes, filename)
        except (PdfGenerationError, EmailError) as e:
            flash(f"Échec de l'envoi : {e}", "error")
            return redirect(url_for("missions.email_mission", mission_id=mission_id))
        repo.set_mission_status(mission_id, "envoyé")
        repo.mark_sent_driver(mission_id)
        flash(f"Ordre de mission envoyé à {', '.join(to_list)}.", "success")
        return redirect(url_for("missions.detail_mission", mission_id=mission_id))

    default_subject, default_body = _driver_email_defaults(mission)
    return render_template(
        "missions/email.html", mission=mission, driver=driver,
        default_subject=default_subject, default_body=default_body,
    )


def _driver_email_defaults(mission):
    """Objet / corps de l'email envoyé au chauffeur d'une mission. Partagé
    entre l'envoi unitaire (page de rédaction) et l'envoi groupé « chaque
    mission à son chauffeur ». Objet : « Ordre de mission du [jour]
    [dd/mm/YYYY] : [prise de service] - [fin de service] ([nom de
    mission]) »."""
    label = fmt_date_full(mission["mission_date"])
    start, end = service_time_range(mission.get("legs") or [])
    name = mission.get("mission_name") or mission["reference"]
    detail = f" : {fmt_time(start)} - {fmt_time(end)} ({name})" if start and end else f" ({name})"
    subject = f"Ordre de mission du {label}{detail}"
    body = (
        f"Bonjour {mission['driver']['first_name']},\n\n"
        f"Veuillez trouver ci-joint votre ordre de mission et le billet collectif "
        f"pour le {label}{detail}.\n\n"
        f"Cordialement,\n{COMPANY['name']}"
    )
    return subject, body


def _bulk_email_defaults(missions):
    """Regroupe les missions sélectionnées par chauffeur (ordre
    d'apparition), trie les dates de chacun, et construit l'objet/corps
    par défaut du bouton « Envoyer à Randstad »."""
    order = []
    groups = {}
    for m in missions:
        driver = m["driver"]
        key = driver["id"]
        if key not in groups:
            groups[key] = {"name": f"{driver['last_name']} {driver['first_name']}", "rows": []}
            order.append(key)
        legs = m.get("legs") or []
        time_range = f"{fmt_time(legs[0]['start_time'])}-{fmt_time(legs[-1]['end_time'])}" if legs else ""
        groups[key]["rows"].append((m["mission_date"], time_range))
    for key in groups:
        groups[key]["rows"].sort(key=lambda r: r[0])

    names = [groups[k]["name"] for k in order]
    subject = "Missions pour " + " + ".join(names)

    lines = ["Bonjour,", "", f"Veuillez trouver ci-joint des missions pour {' + '.join(names)} :", ""]
    for key in order:
        g = groups[key]
        lines.append(f"{g['name']} :")
        lines.append("")
        for mission_date, time_range in g["rows"]:
            row = fmt_date_short(mission_date)
            if time_range:
                row += f" : {time_range}"
            lines.append(row)
        lines.append("")
    lines += [
        "Vous en souhaitant bonne réception.",
        "",
        "Cordialement,",
        COMPANY["name"],
    ]
    return subject, "\n".join(lines)


@bp.route("/envoi-groupe", methods=["GET", "POST"])
def bulk_email():
    """Sélection multiple sur la liste des missions -> bouton "Envoyer à
    Randstad" : un email avec un PDF (Ordre de Mission) par mission en pièce jointe."""
    ids = (request.form if request.method == "POST" else request.args).getlist("mission_ids", type=int)
    missions = [m for m in (repo.get_mission(i) for i in ids) if m]
    if not missions:
        flash("Sélectionnez au moins un ordre de mission.", "error")
        return redirect(url_for("missions.list_missions_view"))

    if request.method == "POST":
        to_list = [e.strip() for e in request.form.get("to", "").split(",") if e.strip()]
        cc_list = [e.strip() for e in request.form.get("cc", "").split(",") if e.strip()]
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "")
        if not to_list or not subject:
            flash("Au moins un destinataire et un objet sont requis.", "error")
            return redirect(url_for("missions.bulk_email", mission_ids=ids))
        try:
            attachments = [generate_mission_pdf(m["id"]) for m in missions]
            send_bulk_email(ids, to_list, cc_list, subject, body, attachments)
        except (PdfGenerationError, EmailError) as e:
            flash(f"Échec de l'envoi : {e}", "error")
            return redirect(url_for("missions.bulk_email", mission_ids=ids))
        for m in missions:
            repo.mark_sent_randstad(m["id"])
        flash(f"{len(missions)} ordre(s) de mission envoyé(s) à {', '.join(to_list)}.", "success")
        return redirect(url_for("missions.list_missions_view"))

    subject, body = _bulk_email_defaults(missions)
    return render_template(
        "missions/bulk_email.html", missions=missions, mission_ids=ids,
        default_to=RANDSTAD_EMAIL, default_subject=subject, default_body=body,
    )


@bp.route("/envoi-chauffeurs", methods=["POST"])
def bulk_email_drivers():
    """Sélection multiple -> un email distinct par mission, adressé au
    chauffeur de cette mission (contrairement à l'envoi Randstad qui
    regroupe tout dans un seul email)."""
    ids = request.form.getlist("mission_ids", type=int)
    missions = [m for m in (repo.get_mission(i) for i in ids) if m]
    if not missions:
        flash("Sélectionnez au moins un ordre de mission.", "error")
        return redirect(url_for("missions.list_missions_view"))

    sent, skipped, failed = [], [], []
    for m in missions:
        driver = m["driver"]
        to = (driver.get("email") or "").strip()
        if not to:
            skipped.append(f"{m['reference']} ({driver['last_name']} : pas d'email)")
            continue
        subject, body = _driver_email_defaults(m)
        try:
            pdf_bytes, filename = generate_mission_pdf(m["id"])
            send_mission_email(m["id"], [to], [], subject, body, pdf_bytes, filename)
        except (PdfGenerationError, EmailError) as e:
            failed.append(f"{m['reference']} : {e}")
            continue
        repo.set_mission_status(m["id"], "envoyé")
        repo.mark_sent_driver(m["id"])
        sent.append(f"{m['reference']} → {to}")

    if sent:
        flash(f"{len(sent)} email(s) envoyé(s) : {', '.join(sent)}.", "success")
    if skipped:
        flash(f"Ignoré(s), chauffeur sans email : {', '.join(skipped)}.", "error")
    if failed:
        flash(f"Échec(s) : {'; '.join(failed)}.", "error")
    return redirect(url_for("missions.list_missions_view"))
