from pathlib import Path

from flask import (
    Blueprint, render_template, request, redirect, url_for, flash, Response, abort
)
from werkzeug.utils import secure_filename

from app import repo
from app.config import COMPANY
from app.pdf_service import generate_mission_pdf, PdfGenerationError, POSITION_BEFORE_OM, POSITION_AFTER_OM, POSITION_AFTER_BC
from app.email_service import send_mission_email, EmailError

bp = Blueprint("missions", __name__, url_prefix="/missions")

ATTACHMENT_POSITIONS = [
    (POSITION_BEFORE_OM, "Avant l'Ordre de mission"),
    (POSITION_AFTER_OM, "Après l'OM, avant le BC (page 2 — recommandé pour la feuille de référence)"),
    (POSITION_AFTER_BC, "Après le Billet collectif"),
]

ALLOWED_ATTACHMENT_EXT = {".pdf", ".png", ".jpg", ".jpeg"}


def _at(lst, i, default=""):
    return lst[i] if i < len(lst) else default


def _parse_legs(form):
    # Indexation "sûre" plutôt que zip() : si un champ optionnel est absent
    # du formulaire pour certaines lignes, on ne désaligne pas les autres.
    starts = form.getlist("leg_start_time[]")
    ends = form.getlist("leg_end_time[]")
    vehicle_ids = form.getlist("leg_vehicle_id[]")
    labels = form.getlist("leg_label[]")
    n = max(len(starts), len(ends), len(vehicle_ids), len(labels))
    legs = []
    for i in range(n):
        s, e, v, l = _at(starts, i).strip(), _at(ends, i).strip(), _at(vehicle_ids, i), _at(labels, i).strip()
        if not s and not e and not l:
            continue
        is_relay = v == "relais"
        legs.append({
            "start_time": s,
            "end_time": e,
            "vehicle_id": int(v) if (v and v.isdigit()) else None,
            "label": l,
            "is_checkpoint": bool(s) and s == e and not is_relay,
            "is_relay": is_relay,
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
        "clients": repo.list_clients(),
        "om_templates": repo.list_templates("OM"),
        "bc_templates": repo.list_templates("BC"),
        "mission": mission,
    }


@bp.route("/")
def list_missions_view():
    driver_id = request.args.get("driver_id", type=int)
    date_from = request.args.get("date_from") or None
    date_to = request.args.get("date_to") or None
    status = request.args.get("status") or None
    missions = repo.list_missions(driver_id=driver_id, date_from=date_from, date_to=date_to, status=status)
    return render_template(
        "missions/list.html", missions=missions, drivers=repo.list_drivers(),
        filters={"driver_id": driver_id, "date_from": date_from, "date_to": date_to, "status": status},
    )


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
        "mission_date": "", "emission_date": "", "price": "", "remarks": "",
        "legs": [], "stops": [],
    }))


@bp.route("/<int:mission_id>")
def detail_mission(mission_id):
    mission = repo.get_mission(mission_id)
    if not mission:
        abort(404)
    emails = repo.list_email_log(mission_id)
    return render_template("missions/detail.html", mission=mission, emails=emails,
                            positions=ATTACHMENT_POSITIONS)


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
    insert_after_page = request.form.get("insert_after_page", type=int)
    if insert_after_page is None:
        insert_after_page = POSITION_AFTER_OM
    repo.add_attachment(
        mission_id, secure_filename(file.filename), content, file.mimetype, insert_after_page
    )
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
        flash(f"OM + BC envoyés à {', '.join(to_list)}.", "success")
        return redirect(url_for("missions.detail_mission", mission_id=mission_id))

    default_subject = f"{COMPANY['name']} — Ordre de mission du {mission['mission_date']}"
    default_body = (
        f"Bonjour {driver['first_name']},\n\n"
        f"Veuillez trouver ci-joint votre ordre de mission et le billet collectif "
        f"pour le {mission['mission_date']}.\n\n"
        f"Cordialement,\n{COMPANY['name']}"
    )
    return render_template(
        "missions/email.html", mission=mission, driver=driver,
        default_subject=default_subject, default_body=default_body,
    )
