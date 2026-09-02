from flask import Blueprint, render_template, request, redirect, url_for, flash

from app import repo

bp = Blueprint("drivers", __name__, url_prefix="/chauffeurs")


def _form_to_data(form):
    return {
        "last_name": form.get("last_name", "").strip().upper(),
        "first_name": form.get("first_name", "").strip(),
        "email": form.get("email", "").strip(),
        "phone": form.get("phone", "").strip() or None,
        "license_number": form.get("license_number", "").strip() or None,
        "active": form.get("active") == "on",
        "notes": form.get("notes", "").strip() or None,
    }


@bp.route("/")
def list_drivers_view():
    drivers = repo.list_drivers()
    return render_template("drivers/list.html", drivers=drivers)


@bp.route("/nouveau", methods=["GET", "POST"])
def new_driver():
    if request.method == "POST":
        data = _form_to_data(request.form)
        if not data["last_name"] or not data["first_name"] or not data["email"]:
            flash("Nom, prénom et email sont obligatoires.", "error")
            return render_template("drivers/form.html", driver=data, is_new=True)
        repo.create_driver(data)
        flash(f"Chauffeur {data['first_name']} {data['last_name']} créé.", "success")
        return redirect(url_for("drivers.list_drivers_view"))
    return render_template("drivers/form.html", driver={"active": True}, is_new=True)


@bp.route("/<int:driver_id>", methods=["GET", "POST"])
def edit_driver(driver_id):
    driver = repo.get_driver(driver_id)
    if not driver:
        flash("Chauffeur introuvable.", "error")
        return redirect(url_for("drivers.list_drivers_view"))
    if request.method == "POST":
        data = _form_to_data(request.form)
        if not data["last_name"] or not data["first_name"] or not data["email"]:
            flash("Nom, prénom et email sont obligatoires.", "error")
            return render_template("drivers/form.html", driver=data, is_new=False, driver_id=driver_id)
        repo.update_driver(driver_id, data)
        flash("Chauffeur mis à jour.", "success")
        return redirect(url_for("drivers.list_drivers_view"))
    return render_template("drivers/form.html", driver=driver, is_new=False, driver_id=driver_id)


@bp.route("/<int:driver_id>/supprimer", methods=["POST"])
def delete_driver(driver_id):
    repo.delete_driver(driver_id)
    flash("Chauffeur supprimé.", "success")
    return redirect(url_for("drivers.list_drivers_view"))
