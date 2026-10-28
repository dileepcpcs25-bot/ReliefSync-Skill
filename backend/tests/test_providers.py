import smtplib

from app.services import notification_providers as prov
from app.services.notification_providers import SmtpEmailProvider, TwilioSmsProvider, get_provider, mask_contact, normalise_phone, valid_email


def test_phone_and_email_validation_and_masking():
    assert normalise_phone("+91 98765-43210") == "+919876543210"
    assert normalise_phone("(044) 2345") is None and normalise_phone("") is None and normalise_phone("+0123456789") is None
    assert valid_email("a@b.co") and not valid_email("a@b") and not valid_email("no at sign")
    assert mask_contact("sms", "+919876543210") == "***********10" and mask_contact("email", "jane@example.org") == "j***@example.org" and mask_contact("in_app", "") == "(in-app)"


def test_get_provider_is_simulator_unless_live(cfg):
    assert get_provider("sms").name == "development-simulator" and get_provider("email").name == "development-simulator"
    cfg(notifications_mode="live")
    assert get_provider("sms").name == "sms-unavailable" and get_provider("email").name == "email-unavailable"
    cfg(twilio_account_sid="AC1", twilio_auth_token="t", twilio_from_number="+1555")
    assert isinstance(get_provider("sms"), TwilioSmsProvider)
    cfg(smtp_host="smtp.example.org", smtp_from="a@example.org")
    assert isinstance(get_provider("email"), SmtpEmailProvider)


def test_twilio_uses_messaging_service_when_configured(net, cfg):
    cfg(notifications_mode="live", twilio_account_sid="AC1", twilio_auth_token="t", twilio_messaging_service_sid="MG123")
    net.add("api.twilio.com", status=201, json={"sid": "SM1", "status": "queued"})
    res = TwilioSmsProvider().send("sms", "+919876543210", "s", "hello")
    assert res.status == "accepted_by_provider" and "MessagingServiceSid=MG123" in net.calls[0].content.decode() and "From=" not in net.calls[0].content.decode()


def test_twilio_error_responses_are_failures(net, cfg):
    cfg(notifications_mode="live", twilio_account_sid="AC1", twilio_auth_token="t", twilio_from_number="+1555")
    net.add("api.twilio.com", status=401, json={"message": "auth"})
    res = TwilioSmsProvider().send("sms", "+919876543210", "s", "hello")
    assert res.status == "failed" and "HTTP 401" in res.detail


class FakeSMTP:
    sent, fail = [], False

    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self):
        pass

    def login(self, u, p):
        pass

    def send_message(self, msg):
        if FakeSMTP.fail:
            raise smtplib.SMTPRecipientsRefused({})
        FakeSMTP.sent.append(msg)


def test_smtp_provider_success_and_failure(monkeypatch, cfg):
    cfg(smtp_host="smtp.example.org", smtp_from="alerts@example.org", smtp_username="u", smtp_password="p")
    monkeypatch.setattr(prov.smtplib, "SMTP", FakeSMTP)
    FakeSMTP.sent, FakeSMTP.fail = [], False
    ok = SmtpEmailProvider().send("email", "x@example.com", "Subject", "Body")
    assert ok.status == "accepted_by_provider" and "not confirmed" in ok.detail and FakeSMTP.sent[0]["To"] == "x@example.com"
    FakeSMTP.fail = True
    bad = SmtpEmailProvider().send("email", "x@example.com", "Subject", "Body")
    assert bad.status == "failed" and "SMTPRecipientsRefused" in bad.detail
