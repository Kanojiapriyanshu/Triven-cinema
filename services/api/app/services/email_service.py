"""Sign-in code delivery over SMTP (any provider: SES, Postmark, SendGrid, Gmail, Hostinger mail)."""
import logging
import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr

from app.core.config import settings

LOGGER = logging.getLogger("triven.email")


class EmailDeliveryError(RuntimeError):
    pass


def build_otp_message(to_address: str, otp: str, ttl_seconds: int) -> EmailMessage:
    minutes = max(1, round(ttl_seconds / 60))
    message = EmailMessage()
    message["Subject"] = f"Your Triven Cinema sign-in code: {otp}"
    message["From"] = formataddr((settings.app_name.replace(" API", ""), settings.smtp_from))
    message["To"] = to_address
    message.set_content(
        f"Your Triven Cinema sign-in code is {otp}.\n\n"
        f"It expires in {minutes} minute{'s' if minutes != 1 else ''}. "
        "If you did not ask for it, you can ignore this email; nobody can sign in without the code.\n"
    )
    return message


def send_otp_email(to_address: str, otp: str, ttl_seconds: int) -> None:
    """Send the code. Failures raise EmailDeliveryError with a safe message; details go to the log only."""
    if not settings.smtp_configured:
        raise EmailDeliveryError("Sign-in email is not configured.")
    message = build_otp_message(to_address, otp, ttl_seconds)
    timeout = max(3.0, float(settings.smtp_timeout_seconds))
    security = settings.smtp_security.strip().lower()
    try:
        if security == "ssl":
            client = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=timeout, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=timeout)
        with client:
            if security == "starttls":
                client.starttls(context=ssl.create_default_context())
            if settings.smtp_username:
                client.login(settings.smtp_username, settings.smtp_password)
            client.send_message(message)
    except Exception as exc:  # noqa: BLE001 - never leak provider details to the browser
        LOGGER.exception("Could not send the sign-in email via %s:%s", settings.smtp_host, settings.smtp_port)
        raise EmailDeliveryError("We could not send the sign-in email. Try again in a moment.") from exc
