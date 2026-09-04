"""
Envoi de l'OM+BC par email, en pièce jointe PDF.

Deux modes, choisis par SMTP_AUTH_METHOD dans .env :

- "basic" (par défaut) : SMTP classique avec identifiant/mot de passe,
  fonctionne avec Gmail (mot de passe d'application), OVH, Infomaniak,
  la plupart des hébergeurs. C'est le mode testé dans cet environnement
  (le code ci-dessous est du smtplib standard).

- "oauth2_o365" : Microsoft 365 / Exchange Online, via l'API **Microsoft
  Graph** (`POST /users/{expéditeur}/sendMail`), en OAuth2 client-
  credentials (msal). On n'utilise volontairement PAS le protocole SMTP
  AUTH classique : il est traité comme une « authentification legacy »
  par Microsoft et bloqué dès que les Security Defaults / Conditional
  Access sont actifs sur le tenant (cas de la plupart des tenants créés
  récemment) — désactiver cette protection tenant-wide juste pour
  l'email est un compromis de sécurité qu'on préfère éviter. Graph est
  une API REST « moderne », non concernée par ce blocage.
  Voir README > Configuration email pour le setup Azure AD complet
  (App registration, permission Graph `Mail.Send`, admin consent).

Un timeout explicite est posé sur les appels réseau : sans lui, un
serveur injoignable (mauvais host, pare-feu, etc.) peut faire attendre
la requête indéfiniment plutôt que d'échouer proprement.
"""
import base64
import json
import smtplib
import urllib.error
import urllib.request
from email.message import EmailMessage

from app import repo
from app.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM_NAME, SMTP_FROM_EMAIL,
    SMTP_AUTH_METHOD, O365_TENANT_ID, O365_CLIENT_ID, O365_CLIENT_SECRET, O365_SENDER_EMAIL,
)

TIMEOUT_SECONDS = 20
GRAPH_BASE = "https://graph.microsoft.com/v1.0"
# Limite documentée de sendMail avec pièces jointes en base64 inline ; au-delà
# il faudrait un upload session (non implémenté ici, cas rare pour des OM+BC).
GRAPH_MAX_MESSAGE_BYTES = 4 * 1024 * 1024


class EmailError(Exception):
    pass


# --------------------------------------------------------- mode "basic"
def _send_via_smtp(msg: EmailMessage):
    with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT_SECONDS) as server:
        server.ehlo()
        server.starttls()
        server.ehlo()
        server.login(SMTP_USER, SMTP_PASS)
        server.send_message(msg)


def _build_message(to_addresses, cc_addresses, subject, body, attachments):
    """attachments : liste de (pdf_bytes, filename)."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = ", ".join(to_addresses)
    if cc_addresses:
        msg["Cc"] = ", ".join(cc_addresses)
    msg.set_content(body)
    for pdf_bytes, pdf_filename in attachments:
        msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)
    return msg


# ----------------------------------------------------- mode "oauth2_o365"
def _get_graph_access_token():
    try:
        import msal
    except ImportError as e:
        raise EmailError(
            "SMTP_AUTH_METHOD=oauth2_o365 nécessite le paquet 'msal' "
            "(déjà dans requirements.txt — redéployez si l'erreur persiste)"
        ) from e
    app = msal.ConfidentialClientApplication(
        O365_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{O365_TENANT_ID}",
        client_credential=O365_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
    if "access_token" not in result:
        raise EmailError(f"Échec d'obtention du jeton Graph : {result.get('error_description')}")
    return result["access_token"]


def _send_via_graph(to_addresses, cc_addresses, subject, body, attachments):
    token = _get_graph_access_token()

    graph_attachments = []
    total_bytes = len(body.encode("utf-8"))
    for pdf_bytes, filename in attachments:
        total_bytes += len(pdf_bytes)
        graph_attachments.append({
            "@odata.type": "#microsoft.graph.fileAttachment",
            "name": filename,
            "contentType": "application/pdf",
            "contentBytes": base64.b64encode(pdf_bytes).decode("ascii"),
        })
    if total_bytes > GRAPH_MAX_MESSAGE_BYTES:
        raise EmailError(
            f"Message trop volumineux pour l'API Graph ({total_bytes // 1024} Ko, limite ~4 Mo) "
            "— réduisez le nombre ou la taille des pièces jointes."
        )

    payload = {
        "message": {
            "subject": subject,
            "body": {"contentType": "Text", "content": body},
            "toRecipients": [{"emailAddress": {"address": a}} for a in to_addresses],
            "attachments": graph_attachments,
        },
        "saveToSentItems": "true",
    }
    if cc_addresses:
        payload["message"]["ccRecipients"] = [{"emailAddress": {"address": a}} for a in cc_addresses]

    req = urllib.request.Request(
        f"{GRAPH_BASE}/users/{O365_SENDER_EMAIL}/sendMail",
        data=json.dumps(payload).encode("utf-8"), method="POST",
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS):
            pass
    except urllib.error.HTTPError as e:
        detail = e.read().decode("utf-8", "ignore")[:500]
        raise EmailError(f"Microsoft Graph a refusé l'envoi ({e.code}) : {detail}") from e
    except Exception as e:
        raise EmailError(f"Microsoft Graph injoignable : {e}") from e


# --------------------------------------------------------------- dispatch
def _send(to_addresses, cc_addresses, subject, body, attachments):
    if SMTP_AUTH_METHOD == "oauth2_o365":
        _send_via_graph(to_addresses, cc_addresses, subject, body, attachments)
    else:
        _send_via_smtp(_build_message(to_addresses, cc_addresses, subject, body, attachments))


def send_mission_email(mission_id, to_addresses, cc_addresses, subject, body, pdf_bytes, pdf_filename):
    """to_addresses / cc_addresses : listes de chaînes email. Une seule
    mission -> un seul PDF joint, journalisé sur cette mission."""
    try:
        _send(to_addresses, cc_addresses, subject, body, [(pdf_bytes, pdf_filename)])
    except Exception as e:
        repo.log_email(
            mission_id, ", ".join(to_addresses), ", ".join(cc_addresses or []),
            subject, body, status="failed", error_message=str(e),
        )
        raise EmailError(str(e)) from e

    repo.log_email(
        mission_id, ", ".join(to_addresses), ", ".join(cc_addresses or []),
        subject, body, status="sent",
    )


def send_bulk_email(mission_ids, to_addresses, cc_addresses, subject, body, attachments):
    """Envoi groupé : plusieurs missions dans un seul email, un PDF par
    mission en pièce jointe. Journalise l'envoi sur chacune des missions
    (visible dans leur historique respectif)."""
    to_str, cc_str = ", ".join(to_addresses), ", ".join(cc_addresses or [])
    try:
        _send(to_addresses, cc_addresses, subject, body, attachments)
    except Exception as e:
        for mission_id in mission_ids:
            repo.log_email(mission_id, to_str, cc_str, subject, body, status="failed", error_message=str(e))
        raise EmailError(str(e)) from e

    for mission_id in mission_ids:
        repo.log_email(mission_id, to_str, cc_str, subject, body, status="sent")
