"""Delivery providers. In DEVELOPMENT mode (the default) the SMS/email providers are replaced by a simulator that
never contacts anyone. In LIVE mode a channel is only usable when its credentials are configured.

Honest statuses:  recorded_in_app (a database record only) | simulated (dev mode, nothing sent) |
accepted_by_provider (the provider API accepted the message - this is NOT proof of delivery to a handset/inbox) |
failed (with the error).  ReliefSync does not receive delivery receipts, so it never reports 'delivered'."""
from __future__ import annotations

import re
import smtplib
from dataclasses import dataclass
from email.message import EmailMessage

from ..config import settings
from . import httpclient
from .httpclient import ExternalApiError

E164 = re.compile(r"^\+[1-9]\d{7,14}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


@dataclass
class ProviderResult:
    status: str
    provider: str
    message_id: str | None = None
    detail: str = ""


def normalise_phone(raw: str) -> str | None:
    cleaned = re.sub(r"[\s().-]", "", raw or "")
    return cleaned if E164.match(cleaned) else None


def valid_email(raw: str) -> bool:
    return bool(EMAIL.match(raw or "")) and len(raw) <= 160


def mask_contact(channel: str, value: str) -> str:
    if channel == "sms":
        return "*" * max(0, len(value) - 2) + value[-2:]
    if channel == "email" and "@" in value:
        name, domain = value.split("@", 1)
        return f"{name[:1]}***@{domain}"
    return "(in-app)"


class SimulatedProvider:
    name = "development-simulator"

    def send(self, channel: str, to: str, subject: str, body: str) -> ProviderResult:
        return ProviderResult("simulated", self.name, None, "Development mode: nothing was sent to any real recipient.")


class TwilioSmsProvider:
    """Twilio Programmable Messaging REST API: POST /2010-04-01/Accounts/{sid}/Messages.json (HTTP basic auth)."""

    name = "twilio-sms"

    def send(self, channel: str, to: str, subject: str, body: str) -> ProviderResult:
        url = f"{settings.twilio_base_url.rstrip('/')}/2010-04-01/Accounts/{settings.twilio_account_sid}/Messages.json"
        data = {"To": to, "Body": body}
        if settings.twilio_messaging_service_sid:
            data["MessagingServiceSid"] = settings.twilio_messaging_service_sid
        else:
            data["From"] = settings.twilio_from_number
        try:
            resp = httpclient.request("POST", url, data=data, auth=(settings.twilio_account_sid, settings.twilio_auth_token), retries=0)
            payload = resp.json()
        except ExternalApiError as exc:
            return ProviderResult("failed", self.name, None, f"Provider error: {exc.message}")
        except ValueError:
            return ProviderResult("failed", self.name, None, "Provider returned an unreadable response")
        return ProviderResult("accepted_by_provider", self.name, payload.get("sid"),
                              f"Twilio accepted the message (status: {payload.get('status', 'unknown')}). Handset delivery is not confirmed.")


class SmtpEmailProvider:
    name = "smtp-email"

    def send(self, channel: str, to: str, subject: str, body: str) -> ProviderResult:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = settings.smtp_from, to, subject
        msg.set_content(body)
        try:
            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=settings.http_timeout_seconds) as smtp:
                if settings.smtp_starttls:
                    smtp.starttls()
                if settings.smtp_username:
                    smtp.login(settings.smtp_username, settings.smtp_password)
                smtp.send_message(msg)
        except (smtplib.SMTPException, OSError) as exc:
            return ProviderResult("failed", self.name, None, f"SMTP error: {type(exc).__name__}")
        return ProviderResult("accepted_by_provider", self.name, None, "The mail server accepted the message. Inbox delivery is not confirmed.")


class UnavailableProvider:
    def __init__(self, channel: str, why: str):
        self.name, self.why = f"{channel}-unavailable", why

    def send(self, channel: str, to: str, subject: str, body: str) -> ProviderResult:
        return ProviderResult("failed", self.name, None, self.why)


def get_provider(channel: str):
    """Provider for sms/email. In development mode ALWAYS the simulator."""
    if not settings.live_mode:
        return SimulatedProvider()
    if channel == "sms":
        return TwilioSmsProvider() if settings.twilio_configured else UnavailableProvider("sms", "Live mode is on but Twilio credentials are not configured.")
    if channel == "email":
        return SmtpEmailProvider() if settings.smtp_configured else UnavailableProvider("email", "Live mode is on but SMTP is not configured.")
    return UnavailableProvider(channel, f"Unsupported channel: {channel}")


def channel_status() -> dict:
    return {
        "mode": settings.notifications_mode,
        "in_app": {"available": True, "note": "Creates a record inside ReliefSync only."},
        "sms": {"available": settings.live_mode and settings.twilio_configured, "configured": settings.twilio_configured,
                "provider": "twilio", "cost_per_message": settings.sms_cost_per_message or None},
        "email": {"available": settings.live_mode and settings.smtp_configured, "configured": settings.smtp_configured,
                  "provider": "smtp", "cost_per_message": settings.email_cost_per_message or None},
        "browser_push": {"available": False, "note": "Not implemented (would require service workers, VAPID keys and per-device consent)."},
    }
