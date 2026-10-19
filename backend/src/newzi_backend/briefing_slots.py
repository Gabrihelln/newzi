"""The day's briefings of one person: the daily briefing plus, on Premium, up to two extra ones.

Slot 1 is the daily briefing of the preferences (``briefing_time``, ``briefing_length``). Slots 2 and 3 live in
``briefing_slots``: each has its own time, an optional theme (one topic, e.g. only Esportes; none means the
person's topics) and a length (``standard`` or ``extended``, which narrates more context per story).
Slots 10 and above are briefings made on request ("Gerar agora"), never scheduled.

Extra slots are kept when a plan ends but are not scheduled: they come back with Premium.
"""
from .timeutil import now_iso

MAIN_SLOT = 1
EXTRA_SLOTS = (2, 3)
ON_DEMAND_FIRST_SLOT = 10
LENGTHS = ("standard", "extended")


def kind_of(slot):
    return "SCHEDULED" if slot == MAIN_SLOT else "EXTRA" if slot in EXTRA_SLOTS else "ON_DEMAND"


def extra_slots(repo, uid):
    return [{"slot": row["slot"], "time": row["delivery_time"], "theme": row["theme"], "length": row["length"], "enabled": bool(row["enabled"])}
            for row in repo.db.execute("SELECT * FROM briefing_slots WHERE user_id=? ORDER BY slot", (uid,))]


def scheduled_slots(repo, uid, prefs=None):
    """Every briefing scheduled for the person each day: slot 1, then the enabled extra ones the plan allows."""
    from .subscriptions import has_premium_features
    prefs = prefs or repo.get_preferences(uid)
    if not prefs:
        return []
    main = {"slot": MAIN_SLOT, "time": prefs["briefing_time"], "theme": None, "length": prefs.get("briefing_length") or "standard", "enabled": True}
    if not has_premium_features(repo, uid):
        return [{**main, "length": "standard"}]
    return [main, *(slot for slot in extra_slots(repo, uid) if slot["enabled"])]


def used_briefing_times(repo, uid):
    return len(scheduled_slots(repo, uid))


def slot_preferences(prefs, slot):
    """The preferences a slot's briefing is composed with: a themed slot follows only its theme."""
    if not slot or not slot.get("theme"):
        return prefs
    return {**prefs, "topics": [slot["theme"]], "content_scope": "selected"}


def slot_for(repo, uid, number, prefs=None):
    """The definition of one slot of the person (None when it does not exist or is not scheduled)."""
    prefs = prefs or repo.get_preferences(uid)
    if number == MAIN_SLOT:
        return next((slot for slot in scheduled_slots(repo, uid, prefs) if slot["slot"] == MAIN_SLOT), None)
    if number >= ON_DEMAND_FIRST_SLOT:
        from .subscriptions import has_premium_features
        return {"slot": number, "time": None, "theme": None,
                "length": (prefs.get("briefing_length") or "standard") if has_premium_features(repo, uid) else "standard", "enabled": True}
    return next((slot for slot in extra_slots(repo, uid) if slot["slot"] == number), None)


def _validate_time(value):
    from .product_backend import validate_briefing_time
    return validate_briefing_time(value)


def save_extra_slots(repo, uid, items):
    """Replace the extra briefings (Premium). ``items``: up to two ``{time, theme, length, enabled}``."""
    from newzi_engine.topic_registry import taxonomy
    from .subscriptions import PremiumRequired, has_premium_features, limit
    if not isinstance(items, list):
        raise ValueError("extra_briefings must be a list")
    if items and not has_premium_features(repo, uid):
        raise PremiumRequired("extra_briefings")
    allowed = max(0, limit(repo, uid, "briefing_times") - 1)
    if len(items) > allowed:
        raise PremiumRequired("extra_briefings", f"your plan allows {allowed} extra briefing(s)")
    prefs = repo.get_preferences(uid) or {}
    registry = taxonomy(); seen = {prefs.get("briefing_time")}; clean = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            raise ValueError("each extra briefing must be an object")
        time = _validate_time(item.get("time"))
        enabled = item.get("enabled", True)
        if not isinstance(enabled, bool):
            raise ValueError("enabled must be true or false")
        if enabled and time in seen:
            raise ValueError("each briefing needs its own time")
        if enabled:
            seen.add(time)
        theme = item.get("theme") or None
        if theme is not None:
            resolved = registry.resolve(theme)
            if not resolved:
                raise ValueError("unknown theme")
            theme = resolved
        length = item.get("length") or "standard"
        if length not in LENGTHS:
            raise ValueError("length must be standard or extended")
        clean.append((uid, EXTRA_SLOTS[index], time, theme, length, int(enabled), now_iso(), now_iso()))
    repo.db.execute("DELETE FROM briefing_slots WHERE user_id=?", (uid,))
    repo.db.executemany("INSERT INTO briefing_slots(user_id,slot,delivery_time,theme,length,enabled,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)", clean)
    # Jobs not started yet follow the new definitions; slots removed today are dropped.
    kept = [row[1] for row in clean if row[5]]
    repo.db.execute("DELETE FROM generation_jobs WHERE user_id=? AND slot IN (2,3) AND status IN ('PENDING','RETRY')" +
                    (f" AND slot NOT IN ({','.join('?' for _ in kept)})" if kept else ""), (uid, *kept))
    for _, slot, time, *_ in clean:
        repo.db.execute("UPDATE generation_jobs SET delivery_time=? WHERE user_id=? AND slot=? AND status IN ('PENDING','RETRY')", (time, uid, slot))
    repo.db.commit()
    return extra_slots(repo, uid)


def public_slots(repo, uid, prefs=None):
    """What Perfil › Resumo diário shows: every slot with its definition and the plan's limits."""
    from newzi_engine.topic_registry import taxonomy
    from .subscriptions import has_premium_features, limit
    prefs = prefs or repo.get_preferences(uid) or {}
    registry = taxonomy()
    premium = has_premium_features(repo, uid)
    def label(theme):
        return registry.nodes.get(theme, {}).get("name") if theme else None
    extras = [{**slot, "theme_label": label(slot["theme"]), "active": premium and slot["enabled"]} for slot in extra_slots(repo, uid)]
    return {"main": {"slot": MAIN_SLOT, "time": prefs.get("briefing_time"), "length": prefs.get("briefing_length") or "standard"},
            "extra": extras, "limit": limit(repo, uid, "briefing_times"), "premium": premium}
