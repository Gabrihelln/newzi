"""Newzi plans: Básico (free) and Premium (monthly or annual), and what each one allows.

Premium is bought through Google Play Billing. The store's notifications (directly or through
RevenueCat) will write the ``subscriptions`` table through a webhook that is not wired yet; until
then nobody is Premium and BILLING_ENABLED stays off, so the app shows the plans without selling.
Every premium rule is decided here, on the server, never only in the app.
"""
import os
from datetime import datetime, timezone

from .timeutil import iso

# Display prices until the store's localized prices reach the app (the store's price is the one charged).
PLANS = [
    {"id": "annual", "name": "Anual", "price": "R$ 119,90", "per": "ano", "monthly_equivalent": "R$ 9,99", "savings_percent": 33},
    {"id": "monthly", "name": "Mensal", "price": "R$ 14,90", "per": "mês"},
]
LIMITS = {"basic": {"briefing_times": 1, "favorite_teams": 1}, "premium": {"briefing_times": 4, "favorite_teams": 10}}
# A cancelled plan keeps Premium until it expires; "grace" is a failed renewal the store is still retrying.
WITH_ACCESS = {"active", "grace", "canceled"}
PREMIUM_BENEFITS = [
    {"title": "Até 4 resumos por dia", "detail": "Você escolhe os horários de cada um"},
    {"title": "Assuntos sem limite", "detail": "Siga todos os temas e subtemas que quiser"},
    {"title": "Salvos ilimitados e offline", "detail": "Leia e ouça mesmo sem internet"},
    {"title": "Alertas personalizados", "detail": "Palavras-chave, assuntos e gols do seu time"},
]


def billing_enabled():
    return os.getenv("BILLING_ENABLED", "").strip().lower() in ("1", "true", "yes")


def subscription_for(repo, uid, now=None):
    """The user's plan, its limits, and the plans on offer."""
    now = iso(now or datetime.now(timezone.utc))
    row = repo.db.execute("SELECT period,status,expires_at,auto_renew FROM subscriptions WHERE user_id=?", (uid,)).fetchone()
    premium = bool(row) and row["status"] in WITH_ACCESS and (row["expires_at"] or "") > now
    tier = "premium" if premium else "basic"
    prefs = repo.get_preferences(uid) or {}
    return {
        "tier": tier,
        "period": row["period"] if premium else None,
        "status": row["status"] if premium else "active",
        "expires_at": row["expires_at"] if premium else None,
        "will_renew": premium and bool(row["auto_renew"]) and row["status"] != "canceled",
        "payment_issue": premium and row["status"] == "grace",
        "limits": LIMITS[tier],
        "usage": {"briefing_times": 1 if prefs.get("briefing_time") else 0},
        "benefits": PREMIUM_BENEFITS,
        "plans": PLANS,
        "purchases_enabled": billing_enabled(),
        # The store requires both on the purchase screen; they are shown once configured.
        "legal": {"terms_url": os.getenv("TERMS_URL") or None, "privacy_url": os.getenv("PRIVACY_URL") or None},
    }
