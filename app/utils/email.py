"""Utilitaire d'envoi d'emails via Brevo (Sendinblue) API v3.
En mode dev sans le SDK, fonctionne en fallback (log).
"""

import os
from markupsafe import escape

BREVO_API_KEY = os.getenv('BREVO_API_KEY', '')
BREVO_SENDER_EMAIL = os.getenv('BREVO_SENDER_EMAIL', 'nicolaskatuta@gmail.com')
BREVO_SENDER_NAME = "EduSchool"

# Tentative d'import du SDK Brevo
BREVO_AVAILABLE = False
try:
    import sib_api_v3_sdk
    from sib_api_v3_sdk.rest import ApiException
    BREVO_AVAILABLE = True
except ImportError:
    print("[EMAIL] Brevo SDK non installe - mode dev (pas d'envoi reel)")
    ApiException = Exception  # fallback


def send_email(to_email, to_name, subject, html_content):
    """Envoie un email transactionnel via Brevo.
    Returns: (success: bool, message_id: str or None)
    """
    try:
        if not BREVO_AVAILABLE or not BREVO_API_KEY:
            print(f"[EMAIL DEV] To: {to_email} | Subject: {subject}")
            return False, None

        config = sib_api_v3_sdk.Configuration()
        config.api_key['api-key'] = BREVO_API_KEY

        api_instance = sib_api_v3_sdk.TransactionalEmailsApi(
            sib_api_v3_sdk.ApiClient(config)
        )

        send_smtp_email = sib_api_v3_sdk.SendSmtpEmail(
            to=[{"email": to_email, "name": to_name}],
            sender={"email": BREVO_SENDER_EMAIL, "name": BREVO_SENDER_NAME},
            subject=subject,
            html_content=html_content,
        )

        api_response = api_instance.send_transac_email(send_smtp_email)
        print(f"[EMAIL] Sent to {to_email} - ID: {api_response.message_id}")
        return True, api_response.message_id
    except Exception as e:
        print(f"[EMAIL] Error: {e}")
        return False, None


def send_password_reset(user, reset_url):
    """Envoie l'email de reinitialisation de mot de passe."""
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: #2B579A; padding: 20px; border-radius: 8px 8px 0 0;">
            <h2 style="color: white; margin: 0;">EduSchool</h2>
        </div>
        <div style="background: #f8f9fa; padding: 30px; border-radius: 0 0 8px 8px; border: 1px solid #dee2e6;">
            <h3>Reinitialisation de votre mot de passe</h3>
            <p>Bonjour <strong>{user.prenom} {user.nom}</strong>,</p>
            <p>Vous avez demande la reinitialisation de votre mot de passe EduSchool.</p>
            <p>Cliquez sur le bouton ci-dessous pour definir un nouveau mot de passe (lien valable 15 minutes) :</p>
            <div style="text-align: center; margin: 25px 0;">
                <a href="{reset_url}" 
                   style="background: #2B579A; color: white; padding: 12px 30px; text-decoration: none; border-radius: 5px; font-size: 16px;">
                   Reinitialiser mon mot de passe
                </a>
            </div>
            <p style="color: #6c757d; font-size: 14px;">
                Si vous n'avez pas demande cette reinitialisation, ignorez cet email.
            </p>
        </div>
    </div>
    """
    return send_email(user.email, f"{user.prenom} {user.nom}", 
                     "EduSchool - Reinitialisation de mot de passe", html)


def send_announcement_notification(user, annonce):
    """Envoie une notification pour une annonce ciblee."""
    color = '#dc3545' if annonce.priorite == 'urgente' else '#fd7e14' if annonce.priorite == 'importante' else '#2B579A'
    html = f"""
    <div style="font-family: Arial, sans-serif; max-width: 600px; margin: 0 auto; padding: 20px;">
        <div style="background: {color}; padding: 15px 20px; border-radius: 8px 8px 0 0;">
            <h3 style="color: white; margin: 0;">{annonce.titre}</h3>
        </div>
        <div style="background: white; padding: 25px; border-radius: 0 0 8px 8px; border: 1px solid #dee2e6;">
            <p>Bonjour <strong>{user.prenom} {user.nom}</strong>,</p>
            <p>Une nouvelle annonce de l'administration :</p>
            <div style="background: #f8f9fa; padding: 15px; border-left: 4px solid #2B579A; margin: 15px 0;">
                {escape(annonce.contenu).replace(chr(10), '<br>')}
            </div>
            <p style="color: #6c757d; font-size: 14px;">
                Priorite: <strong>{annonce.priorite.upper()}</strong> | 
                Publie par: {annonce.author.nom_complet if annonce.author else 'Administration'}
            </p>
        </div>
    </div>
    """
    return send_email(user.email, f"{user.prenom} {user.nom}",
                     f"EduSchool - {annonce.titre}", html)
