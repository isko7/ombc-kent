from flask import Blueprint, render_template, request, redirect, url_for, flash

from app import repo

bp = Blueprint("vehicles", __name__, url_prefix="/vehicules")


def _form_to_data(form):
    seats = form.get("seats", "").strip()
    return {
        "name": form.get("name", "").strip() or None,
        "plate": form.get("plate", "").strip().upper(),
        "seats": int(seats) if seats.isdigit() else None,
        "active": form.get("active") == "on",
        "notes": form.get("notes", "").strip() or None,
    }


@bp.route("/")
def list_vehicles_view():
    vehicles = repo.list_vehicles()
    return render_template("vehicles/list.html", vehicles=vehicles)


@bp.route("/nouveau", methods=["GET", "POST"])
def new_vehicle():
    if request.method == "POST":
        data = _form_to_data(request.form)
        if not data["plate"]:
            flash("L'immatriculation est obligatoire.", "error")
            return render_template("vehicles/form.html", vehicle=data, is_new=True)
        repo.create_vehicle(data)
        flash(f"Véhicule {data['plate']} créé.", "success")
        return redirect(url_for("vehicles.list_vehicles_view"))
    return render_template("vehicles/form.html", vehicle={"active": True}, is_new=True)


@bp.route("/<int:vehicle_id>", methods=["GET", "POST"])
def edit_vehicle(vehicle_id):
    vehicle = repo.get_vehicle(vehicle_id)
    if not vehicle:
        flash("Véhicule introuvable.", "error")
        return redirect(url_for("vehicles.list_vehicles_view"))
    if request.method == "POST":
        data = _form_to_data(request.form)
        if not data["plate"]:
            flash("L'immatriculation est obligatoire.", "error")
            return render_template("vehicles/form.html", vehicle=data, is_new=False, vehicle_id=vehicle_id)
        repo.update_vehicle(vehicle_id, data)
        flash("Véhicule mis à jour.", "success")
        return redirect(url_for("vehicles.list_vehicles_view"))
    return render_template("vehicles/form.html", vehicle=vehicle, is_new=False, vehicle_id=vehicle_id)


@bp.route("/<int:vehicle_id>/supprimer", methods=["POST"])
def delete_vehicle(vehicle_id):
    repo.delete_vehicle(vehicle_id)
    flash("Véhicule supprimé.", "success")
    return redirect(url_for("vehicles.list_vehicles_view"))
