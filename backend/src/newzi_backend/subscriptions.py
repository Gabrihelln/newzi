"""Newzi plans: Básico (free) and Premium (monthly or annual), and what each one allows.

Premium is bought in the store (App Store, later Google Play) through RevenueCat, whose webhook and the app's sync
call write the ``subscriptions`` table (``revenuecat.py``). BILLING_ENABLED tells the app it may sell; while it is
off the app shows the plans without selling.

The Premium limits only apply with PREMIUM_ENFORCED on. While it is off (until purchases work) everyone keeps
every feature, so a deploy never takes away what people use today; ``backend/premium_test_account.py`` marks an
account Premium (or Básico) to test both sides with it on. Every premium rule is decided here, on the server,
never only in the app.
"""
import os
from datetime import datetime, timedelta, timezone

from .timeutil import iso

# Display prices until the store's localized prices reach the app (the store's price is the one charged).
PLANS = [
    {"id": "annual", "name": "Anual", "price": "R$ 119,90", "per": "ano", "monthly_equivalent": "R$ 9,99", "savings_percent": 33},
    {"id": "monthly", "name": "Mensal", "price": "R$ 14,90", "per": "mês"},
]
# None means no limit. briefing_times counts the daily briefing plus the extra ones.
LIMITS = {
    "basic": {"briefing_times": 1, "favorite_teams": 1, "history_days": 7, "on_demand_per_day": 0, "keyword_alerts": 0,
              "followed_stories": 0, "collections": 0},
    "premium": {"briefing_times": 3, "favorite_teams": 10, "history_days": None, "on_demand_per_day": 5, "keyword_alerts": 20,
                "followed_stories": 30, "collections": 30},
}
# What the app unlocks. The app asks the server (entitlements) and never decides on its own.
FEATURES = ("extra_briefings", "themed_briefings", "on_demand_briefing", "extended_briefing", "offline_downloads", "audio_queue",
            "premium_widgets", "live_activities", "team_reminders", "match_audio", "keyword_alerts", "story_follow",
            "collections", "full_history", "briefing_search")
# A cancelled plan keeps Premium until it expires; "grace" is a failed renewal the store is still retrying.
WITH_ACCESS = {"active", "grace", "canceled"}
PREMIUM_BENEFITS = [
    {"title": "Até 3 resumos por dia", "detail": "Cada um no seu horário, com todos os assuntos ou só um tema"},
    {"title": "Resumo na hora e estendido", "detail": "Gere um resumo quando quiser, ou ouça a versão com mais contexto"},
    {"title": "Alertas personalizados", "detail": "Palavras-chave e novidades das histórias que você acompanha"},
    {"title": "Futebol completo", "detail": "Até 10 times, lembrete antes do jogo e resumo em áudio no fim"},
    {"title": "Salvos e histórico sem limite", "detail": "Coleções, offline, histórico completo e busca nos resumos"},
    {"title": "Widgets e placar ao vivo", "detail": "Widgets por assunto ou time e o jogo na tela de bloqueio do iPhone"},
]


class PremiumRequired(Exception):
    """A Básico account asked for a Premium feature (or went past a Básico limit)."""
    def __init__(self, feature, message=None):
        super().__init__(message or "this feature is part of Newzi Premium")
        self.feature = feature


def billing_enabled():
    return os.getenv("BILLING_ENABLED", "").strip().lower() in ("1", "true", "yes")


def premium_enforced():
    return os.getenv("PREMIUM_ENFORCED", "").strip().lower() in ("1", "true", "yes")


def _row(repo, uid):
    return repo.db.execute("SELECT period,status,expires_at,auto_renew FROM subscriptions WHERE user_id=?", (uid,)).fetchone()


def _active(row, now):
    return bool(row) and row["status"] in WITH_ACCESS and (row["expires_at"] or "") > now


def is_premium(repo, uid, now=None):
    """Whether the account holds a Premium plan right now."""
    return _active(_row(repo, uid), iso(now or datetime.now(timezone.utc)))


def has_premium_features(repo, uid, now=None):
    """Whether Premium features are open to the account: it is Premium, or the limits are not enforced yet."""
    return not premium_enforced() or is_premium(repo, uid, now)


def limits_for(repo, uid, now=None):
    return LIMITS["premium" if has_premium_features(repo, uid, now) else "basic"]


def limit(repo, uid, name, now=None):
    return limits_for(repo, uid, now)[name]


def require(repo, uid, feature):
    """Raise PremiumRequired unless the account may use ``feature``."""
    if feature not in FEATURES:
        raise ValueError(f"unknown premium feature: {feature}")
    if not has_premium_features(repo, uid):
        raise PremiumRequired(feature)


def entitlements(repo, uid, now=None):
    """What the account may use: the app shows locks and Premium sheets from this, never on its own."""
    unlocked = has_premium_features(repo, uid, now)
    return {"premium": unlocked, "enforced": premium_enforced(), "limits": LIMITS["premium" if unlocked else "basic"],
            "features": {name: unlocked for name in FEATURES}}


def subscription_for(repo, uid, now=None):
    """The user's plan, what it unlocks, and the plans on offer."""
    now = iso(now or datetime.now(timezone.utc))
    row = _row(repo, uid)
    premium = _active(row, now)
    tier = "premium" if premium else "basic"
    from .briefing_slots import used_briefing_times
    return {
        "tier": tier,
        "period": row["period"] if premium else None,
        "status": row["status"] if premium else "active",
        "expires_at": row["expires_at"] if premium else None,
        "will_renew": premium and bool(row["auto_renew"]) and row["status"] != "canceled",
        "payment_issue": premium and row["status"] == "grace",
        "limits": LIMITS[tier],
        "usage": {"briefing_times": used_briefing_times(repo, uid)},
        "entitlements": entitlements(repo, uid),
        "benefits": PREMIUM_BENEFITS,
        "plans": PLANS,
        "purchases_enabled": billing_enabled(),
        # The store requires both on the purchase screen; they are shown once configured.
        "legal": {"terms_url": os.getenv("TERMS_URL") or None, "privacy_url": os.getenv("PRIVACY_URL") or None},
    }


def grant_manual(repo, uid, days=30, period="monthly"):
    """Mark an account Premium for ``days`` (tests and support; the store webhook writes real plans)."""
    now = datetime.now(timezone.utc)
    repo.db.execute("""INSERT INTO subscriptions(user_id,period,status,store,product_id,purchase_token,started_at,expires_at,auto_renew,updated_at)
        VALUES(?,?,'active','manual',NULL,NULL,?,?,0,?) ON CONFLICT(user_id) DO UPDATE SET period=excluded.period,status='active',
        store='manual',started_at=excluded.started_at,expires_at=excluded.expires_at,auto_renew=0,updated_at=excluded.updated_at""",
        (uid, period, iso(now), iso(now + timedelta(days=days)), iso(now)))
    repo.db.commit()


def revoke_manual(repo, uid):
    repo.db.execute("DELETE FROM subscriptions WHERE user_id=?", (uid,))
    repo.db.commit()
