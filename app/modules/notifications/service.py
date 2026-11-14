import logging
import smtplib
from email.message import EmailMessage

from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import SessionLocal

from .models import EmailLog, Notification

log = logging.getLogger("app.mail")


def send_mail(to: str, subject: str, body: str, kind: str, dev_hint: str = "") -> None:
    """Send an email (or log it when SMTP is not configured) and record the attempt. Runs in a background task."""
    status, error = "sent", ""
    if not settings.smtp_host:
        status = "logged"
        if dev_hint and not settings.is_production:
            log.warning("EMAIL (%s) to %s not sent, SMTP is not configured. %s", kind, to, dev_hint)
        else:
            log.warning("EMAIL (%s) to %s not sent: SMTP is not configured", kind, to)
    else:
        msg = EmailMessage()
        msg["Subject"], msg["From"], msg["To"] = subject, settings.smtp_from or settings.smtp_user, to
        msg.set_content(body)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=15) as smtp:
                smtp.starttls()
                if settings.smtp_user:
                    smtp.login(settings.smtp_user, settings.smtp_password)
                smtp.send_message(msg)
        except Exception as exc:
            status, error = "failed", str(exc)[:300]
            log.exception("could not send %s email", kind)
    with SessionLocal() as db:
        db.add(EmailLog(to_address=to[:254], subject=subject[:200], kind=kind, status=status, error=error))
        db.commit()


def send_reset_email(to: str, link: str) -> None:
    send_mail(to, f"Reset your {settings.business_name} admin password",
              "Someone asked to reset the admin password.\n\n"
              f"Open this link within 15 minutes (it works once): {link}\n\n"
              "If you did not ask for this, ignore this email. Your password has not changed.",
              "password_reset", dev_hint=f"Reset link: {link}")


def notify_new_request(db: Session, req) -> None:
    db.add(Notification(kind="new_request", request_id=req.id,
                        message=f"New request {req.code}: {req.service_name} from {req.customer.name}"))
