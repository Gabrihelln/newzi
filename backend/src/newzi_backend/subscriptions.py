"""Newzi plans: Básico (free) and Premium (monthly or annual), and what each one allows.

Premium is bought in the store (App Store, later Google Play) through RevenueCat, whose webhook and the app's sync
call write the ``subscriptions`` table (``revenuecat.py``). BILLING_ENABLED tells the app it may sell; while it is
off the app shows the plans without selling.

Premium also comes from ``premium_grants``: a courtesy given from the panel (painel.newzi.app) or by
``backend/premium_test_account.py``, from a start date to an end date. It lives in its own table, so a store
purchase and a courtesy never overwrite each other; an account is Premium while either is valid.

The Premium limits only apply with PREMIUM_ENFORCED on. While it is off (until purchases work) everyone keeps
every feature, so a deploy never takes away what people use today; ``backend/premium_test_account.py`` marks an
account Premium (or Básico) to test both sides with it on. Every premium rule is decided here, on the server,
never only in the app.
"""
import os
import uuid
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
    return repo.db.execute("SELECT period,status,expires_at,auto_renew,store FROM subscriptions WHERE user_id=?", (uid,)).fetchone()


def _active(row, now):
    return bool(row) and row["status"] in WITH_ACCESS and (row["expires_at"] or "") > now


def current_grant(repo, uid, now):
    """The courtesy valid at ``now`` (ISO) that lasts longest, or None."""
    return repo.db.execute("""SELECT id,starts_at,ends_at,reason FROM premium_grants WHERE user_id=? AND revoked_at IS NULL
        AND starts_at<=? AND ends_at>? ORDER BY ends_at DESC LIMIT 1""", (uid, now, now)).fetchone()


def is_premium(repo, uid, now=None):
    """Whether the account holds Premium right now: a store plan or a valid courtesy."""
    now = iso(now or datetime.now(timezone.utc))
    return _active(_row(repo, uid), now) or current_grant(repo, uid, now) is not None


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
    store = _active(row, now)
    # The store plan wins when both exist (it renews and can be managed in the store).
    grant = None if store else current_grant(repo, uid, now)
    premium = store or grant is not None
    tier = "premium" if premium else "basic"
    from .briefing_slots import used_briefing_times
    return {
        "tier": tier,
        "period": row["period"] if store else None,
        "status": row["status"] if store else "active",
        "expires_at": row["expires_at"] if store else grant["ends_at"] if grant else None,
        "will_renew": store and bool(row["auto_renew"]) and row["status"] != "canceled",
        "payment_issue": store and row["status"] == "grace",
        "source": "store" if store else "courtesy" if grant else None,
        "limits": LIMITS[tier],
        "usage": {"briefing_times": used_briefing_times(repo, uid)},
        "entitlements": entitlements(repo, uid),
        "benefits": PREMIUM_BENEFITS,
        "plans": PLANS,
        "purchases_enabled": billing_enabled(),
        # The store requires both on the purchase screen; they are shown once configured.
        "legal": {"terms_url": os.getenv("TERMS_URL") or None, "privacy_url": os.getenv("PRIVACY_URL") or None},
    }


# ------------------------------------------------------------- courtesy Premium (premium_grants)
GRANT_REASONS = ("cortesia", "parceria", "suporte", "teste", "outro")


def _clean_grant(starts_at, ends_at, reason, note):
    if not starts_at or not ends_at or ends_at <= starts_at:
        raise ValueError("the end date must come after the start date")
    if reason not in GRANT_REASONS:
        raise ValueError("reason must be one of: " + ", ".join(GRANT_REASONS))
    return (str(note or "").strip()[:300] or None)


def add_grant(repo, uid, starts_at, ends_at, reason="cortesia", note=None, granted_by=None, now=None):
    """Give ``uid`` Premium from ``starts_at`` to ``ends_at`` (ISO, UTC); returns the grant id."""
    note = _clean_grant(starts_at, ends_at, reason, note)
    stamp = iso(now or datetime.now(timezone.utc))
    grant_id = "grant_" + uuid.uuid4().hex
    repo.db.execute("""INSERT INTO premium_grants(id,user_id,starts_at,ends_at,reason,note,granted_by,created_at,updated_at)
        VALUES(?,?,?,?,?,?,?,?,?)""", (grant_id, uid, starts_at, ends_at, reason, note, granted_by, stamp, stamp))
    repo.db.commit()
    return grant_id


def update_grant(repo, grant_id, starts_at, ends_at, reason, note, now=None):
    note = _clean_grant(starts_at, ends_at, reason, note)
    changed = repo.db.execute("""UPDATE premium_grants SET starts_at=?,ends_at=?,reason=?,note=?,updated_at=?
        WHERE id=? AND revoked_at IS NULL""", (starts_at, ends_at, reason, note, iso(now or datetime.now(timezone.utc)), grant_id)).rowcount
    repo.db.commit()
    return changed == 1


def revoke_grant(repo, grant_id, revoked_by=None, now=None):
    """End a courtesy now (it stays in the history)."""
    stamp = iso(now or datetime.now(timezone.utc))
    changed = repo.db.execute("UPDATE premium_grants SET revoked_at=?,revoked_by=?,updated_at=? WHERE id=? AND revoked_at IS NULL",
                              (stamp, revoked_by, stamp, grant_id)).rowcount
    repo.db.commit()
    return changed == 1


def grant_status(row, now):
    """ativo, agendado, encerrado or retirado, for the panel."""
    if row["revoked_at"]:
        return "retirado"
    if row["starts_at"] > now:
        return "agendado"
    return "ativo" if row["ends_at"] > now else "encerrado"


def grant_manual(repo, uid, days=30, period="monthly"):
    """Mark an account Premium for ``days`` from now (tests and support; the store webhook writes real plans)."""
    now = datetime.now(timezone.utc)
    return add_grant(repo, uid, iso(now), iso(now + timedelta(days=days)), "teste", granted_by="script", now=now)


def revoke_manual(repo, uid):
    """End every courtesy of the account now; a store plan is left alone."""
    for row in repo.db.execute("SELECT id FROM premium_grants WHERE user_id=? AND revoked_at IS NULL", (uid,)).fetchall():
        revoke_grant(repo, row["id"], "script")
