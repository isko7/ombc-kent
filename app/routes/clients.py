from flask import Blueprint, render_template, request, redirect, url_for, flash

from app import repo

bp = Blueprint("clients", __name__, url_prefix="/clients")


def _form_to_data(form):
    return {
        "name": form.get("name", "").strip(),
        "address": form.get("address", "").strip() or None,
        "postal_code": form.get("postal_code", "").strip() or None,
        "city": form.get("city", "").strip() or None,
        "phone": form.get("phone", "").strip() or None,
        "email": form.get("email", "").strip() or None,
        "notes": form.get("notes", "").strip() or None,
    }


@bp.route("/")
def list_clients_view():
    clients = repo.list_clients()
    return render_template("clients/list.html", clients=clients)


@bp.route("/nouveau", methods=["GET", "POST"])
def new_client():
    if request.method == "POST":
        data = _form_to_data(request.form)
        if not data["name"]:
            flash("Le nom est obligatoire.", "error")
            return render_template("clients/form.html", client=data, is_new=True)
        repo.create_client(data)
        flash(f"Client {data['name']} créé.", "success")
        return redirect(url_for("clients.list_clients_view"))
    return render_template("clients/form.html", client={}, is_new=True)


@bp.route("/<int:client_id>", methods=["GET", "POST"])
def edit_client(client_id):
    client = repo.get_client(client_id)
    if not client:
        flash("Client introuvable.", "error")
        return redirect(url_for("clients.list_clients_view"))
    if request.method == "POST":
        data = _form_to_data(request.form)
        if not data["name"]:
            flash("Le nom est obligatoire.", "error")
            return render_template("clients/form.html", client=data, is_new=False, client_id=client_id)
        repo.update_client(client_id, data)
        flash("Client mis à jour.", "success")
        return redirect(url_for("clients.list_clients_view"))
    return render_template("clients/form.html", client=client, is_new=False, client_id=client_id)


@bp.route("/<int:client_id>/supprimer", methods=["POST"])
def delete_client(client_id):
    repo.delete_client(client_id)
    flash("Client supprimé.", "success")
    return redirect(url_for("clients.list_clients_view"))
