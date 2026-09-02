"""
Génération du PDF final d'une mission : OM (page 1) + pièces jointes
positionnées + BC (dernières pages), à partir des templates HTML/Jinja2
stockés en base.

Pipeline :
  1. Charger le template actif (ou celui choisi sur la mission) pour OM et BC
  2. Construire le contexte de données (driver, legs/stops, société...)
  3. Rendre le HTML avec Jinja2
  4. Convertir chaque HTML en PDF avec wkhtmltopdf (sous-processus, stdin/stdout)
  5. Fusionner OM + pièces jointes (triées par position d'insertion) + BC avec pypdf

Remplacer le moteur HTML -> PDF (WeasyPrint, Playwright/Chromium...) ne
touche que render_html_to_pdf().
"""
import base64
import subprocess
from io import BytesIO

from jinja2 import Template
from pypdf import PdfReader, PdfWriter
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from PIL import Image

from app import repo
from app.config import COMPANY, OM_LEGAL_REF, BC_LEGAL_REF, WKHTMLTOPDF_BIN, UPLOADS_DIR, BASE_DIR
from app.utils import fmt_time, fmt_date_short, fmt_date_long, day_label

LOGO_PATH = BASE_DIR / "app" / "static" / "img" / "logo.png"
_logo_b64_cache = None

# Valeurs de "insert_after_page" utilisées par le formulaire de pièces
# jointes (voir routes/missions.py) pour les 3 zones d'insertion possibles.
POSITION_BEFORE_OM = 0
POSITION_AFTER_OM = 1      # juste après l'OM = page 2, comme les documents d'origine
POSITION_AFTER_BC = 9999   # après tout, à la fin du document


class PdfGenerationError(Exception):
    pass


def get_logo_base64():
    global _logo_b64_cache
    if _logo_b64_cache is None:
        _logo_b64_cache = base64.b64encode(LOGO_PATH.read_bytes()).decode("ascii")
    return _logo_b64_cache


def render_html_to_pdf(html: str) -> bytes:
    """Convertit une chaîne HTML en octets PDF via wkhtmltopdf (stdin/stdout)."""
    proc = subprocess.run(
        [WKHTMLTOPDF_BIN, "--quiet", "--enable-local-file-access", "-", "-"],
        input=html.encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    if proc.returncode != 0 or not proc.stdout:
        raise PdfGenerationError(
            f"wkhtmltopdf a échoué (code {proc.returncode}): {proc.stderr.decode('utf-8', 'ignore')[:500]}"
        )
    return proc.stdout


def _default_passenger_count(stops):
    pec = sum(s.get("passenger_count") or 1 for s in stops if s["stop_type"] == "prise_en_charge")
    dep = sum(s.get("passenger_count") or 1 for s in stops if s["stop_type"] == "depose")
    return max(pec, dep)


def build_om_context(mission):
    driver = mission["driver"]
    legs = []
    for leg in mission["legs"]:
        legs.append({
            "start_time": fmt_time(leg["start_time"]),
            "end_time": fmt_time(leg["end_time"]),
            "vehicle": leg.get("vehicle_plate"),
            "label": leg["label"],
            "is_checkpoint": bool(leg["is_checkpoint"]),
        })
    return {
        "logo_base64": get_logo_base64(),
        "company": COMPANY,
        "om_legal_ref": OM_LEGAL_REF,
        "driver_name": f"{driver['last_name']} {driver['first_name']}",
        "mission_day_label": day_label(mission["mission_date"]),
        "mission_date_label": fmt_date_long(mission["mission_date"]),
        "legs": legs,
        "remarks": mission.get("remarks") or "",
    }


def build_bc_context(mission):
    driver = mission["driver"]
    client = mission.get("client")
    stops = mission["stops"]
    stop_ctx = []
    for s in stops:
        stop_ctx.append({
            "stop_type": s["stop_type"],
            "date_label": fmt_date_short(s["stop_date"]),
            "time": fmt_time(s["stop_time"]),
            "address": s["address"],
            "city": s.get("city") or "",
        })
    return {
        "logo_base64": get_logo_base64(),
        "company": COMPANY,
        "bc_legal_ref": BC_LEGAL_REF,
        "motif": mission.get("motif") or "Transport Occasionnel",
        "driver_name": f"{driver['last_name']} {driver['first_name']}",
        "stops": stop_ctx,
        "passenger_count": _default_passenger_count(stops),
        "price": mission.get("price") or "",
        "client": {
            "name": client["name"],
            "address": client.get("address") or "",
            "postal_code": client.get("postal_code") or "",
            "city": client.get("city") or "",
            "phone": client.get("phone") or client.get("email") or "",
        } if client else None,
        "emission_date_label": fmt_date_long(mission.get("emission_date") or mission["mission_date"]),
    }


def render_template_string(source_html: str, context: dict) -> bytes:
    html = Template(source_html).render(**context)
    return render_html_to_pdf(html)


def _attachment_to_pdf_bytes(attachment) -> bytes:
    path = UPLOADS_DIR / attachment["stored_filename"]
    content_type = (attachment.get("content_type") or "").lower()
    if content_type == "application/pdf" or attachment["filename"].lower().endswith(".pdf"):
        return path.read_bytes()
    # Image (jpg/png/...) -> on l'enveloppe dans une page A4 pour l'insérer proprement.
    img = Image.open(path)
    img = img.convert("RGB")
    buf = BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    page_w, page_h = A4
    margin = 20
    max_w, max_h = page_w - 2 * margin, page_h - 2 * margin
    scale = min(max_w / img.width, max_h / img.height)
    draw_w, draw_h = img.width * scale, img.height * scale
    x = (page_w - draw_w) / 2
    y = (page_h - draw_h) / 2
    c.drawImage(path, x, y, width=draw_w, height=draw_h)
    c.showPage()
    c.save()
    return buf.getvalue()


def generate_mission_pdf(mission_id: int):
    """Retourne (pdf_bytes, filename) pour la mission donnée."""
    mission = repo.get_mission(mission_id)
    if not mission:
        raise PdfGenerationError("Mission introuvable")

    om_template = (
        repo.get_template(mission["om_template_id"]) if mission.get("om_template_id")
        else repo.get_active_template("OM")
    )
    bc_template = (
        repo.get_template(mission["bc_template_id"]) if mission.get("bc_template_id")
        else repo.get_active_template("BC")
    )
    if not om_template or not bc_template:
        raise PdfGenerationError("Aucun template actif pour l'OM ou le BC (voir Réglages > Templates)")

    om_pdf = render_template_string(om_template["definition_html"], build_om_context(mission))
    bc_pdf = render_template_string(bc_template["definition_html"], build_bc_context(mission))

    writer = PdfWriter()
    om_pages = list(PdfReader(BytesIO(om_pdf)).pages)
    bc_pages = list(PdfReader(BytesIO(bc_pdf)).pages)

    # Trois zones d'insertion pour les pièces jointes (voir POSITION_* dans
    # ce module, utilisées par le formulaire) : avant l'OM, entre l'OM et le
    # BC (par défaut, ex. la feuille de référence qui devient la page 2
    # comme dans les documents d'origine), après le BC. À l'intérieur d'une
    # même zone, l'ordre choisi par l'utilisateur (position) est respecté.
    attachments = sorted(mission["attachments"], key=lambda a: a["position"])
    before_om, between, after_bc = [], [], []
    for att in attachments:
        pages = list(PdfReader(BytesIO(_attachment_to_pdf_bytes(att))).pages)
        if att["insert_after_page"] <= POSITION_BEFORE_OM:
            before_om.extend(pages)
        elif att["insert_after_page"] >= POSITION_AFTER_BC:
            after_bc.extend(pages)
        else:
            between.extend(pages)

    for p in before_om:
        writer.add_page(p)
    for p in om_pages:
        writer.add_page(p)
    for p in between:
        writer.add_page(p)
    for p in bc_pages:
        writer.add_page(p)
    for p in after_bc:
        writer.add_page(p)

    buf = BytesIO()
    writer.write(buf)

    driver = mission["driver"]
    date_compact = (mission["mission_date"] or "").replace("-", "")
    filename = f"{driver['last_name'].upper()}_{date_compact}.pdf"
    return buf.getvalue(), filename
