"""
Envoi de l'OM+BC par email, en pièce jointe PDF.

Deux modes, choisis par SMTP_AUTH_METHOD dans .env :

- "basic" (par défaut) : SMTP classique avec identifiant/mot de passe,
  fonctionne avec Gmail (mot de passe d'application), OVH, Infomaniak,
  la plupart des hébergeurs. C'est le mode testé dans cet environnement
  (le code ci-dessous est du smtplib standard).

- "oauth2_o365" : Microsoft 365 / Exchange Online a désactivé
  l'authentification SMTP par mot de passe ; il faut un jeton OAuth2
  (flux "client credentials" avec msal). Nécessite le paquet optionnel
  `msal` (voir requirements-optional.txt) — non testé dans ce
  bac à sable (pas d'accès réseau ici), mais suit le schéma standard
  documenté par Microsoft pour SMTP AUTH XOAUTH2.

Un timeout explicite est posé sur la connexion SMTP : sans lui, un
serveur SMTP injoignable (mauvais host, pare-feu, etc.) peut faire
attendre la requête indéfiniment plutôt que d'échouer proprement.
"""
import smtplib
from email.message import EmailMessage

from app import repo
from app.config import (
    SMTP_HOST, SMTP_PORT, SMTP_USER, SMTP_PASS, SMTP_FROM_NAME, SMTP_FROM_EMAIL,
    SMTP_AUTH_METHOD, O365_TENANT_ID, O365_CLIENT_ID, O365_CLIENT_SECRET, O365_SENDER_EMAIL,
)

SMTP_TIMEOUT_SECONDS = 20


class EmailError(Exception):
    pass


def _get_o365_access_token():
    try:
        import msal
    except ImportError as e:
        raise EmailError(
            "SMTP_AUTH_METHOD=oauth2_o365 nécessite le paquet 'msal' "
            "(pip install msal) — voir requirements-optional.txt"
        ) from e
    app = msal.ConfidentialClientApplication(
        O365_CLIENT_ID,
        authority=f"https://login.microsoftonline.com/{O365_TENANT_ID}",
        client_credential=O365_CLIENT_SECRET,
    )
    result = app.acquire_token_for_client(scopes=["https://outlook.office365.com/.default"])
    if "access_token" not in result:
        raise EmailError(f"Échec d'obtention du jeton O365 : {result.get('error_description')}")
    return result["access_token"]


def _build_xoauth2_string(user, token):
    return f"user={user}\x01auth=Bearer {token}\x01\x01"


def _send_via_smtp(msg: EmailMessage):
    if SMTP_AUTH_METHOD == "oauth2_o365":
        token = _get_o365_access_token()
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            auth_string = _build_xoauth2_string(O365_SENDER_EMAIL, token)
            server.docmd("AUTH", "XOAUTH2 " + smtplib.base64.b64encode(auth_string.encode()).decode())
            server.send_message(msg)
    else:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(SMTP_USER, SMTP_PASS)
            server.send_message(msg)


def send_mission_email(mission_id, to_addresses, cc_addresses, subject, body, pdf_bytes, pdf_filename):
    """to_addresses / cc_addresses : listes de chaînes email."""
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = f"{SMTP_FROM_NAME} <{SMTP_FROM_EMAIL}>"
    msg["To"] = ", ".join(to_addresses)
    if cc_addresses:
        msg["Cc"] = ", ".join(cc_addresses)
    msg.set_content(body)
    msg.add_attachment(pdf_bytes, maintype="application", subtype="pdf", filename=pdf_filename)

    try:
        _send_via_smtp(msg)
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
