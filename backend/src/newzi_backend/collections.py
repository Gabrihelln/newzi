"""Collections of saved stories (Premium): named folders such as "Para ler no fim de semana" or "Eleições".

A story in a collection is always a saved story: adding one saves it, and removing it from Salvos takes it out of
every collection. A collection made on Premium stays readable after the plan ends; creating and filling them is
Premium.
"""
import json
import uuid

from .timeutil import now_iso

MAX_NAME = 40


def CollectionError(code, message):
    from .product_backend import ApiError
    return ApiError(code, message, 409 if code in ("COLLECTION_EXISTS", "STORY_NOT_SAVED") else 400)


def _name(value):
    name = " ".join(str(value or "").split())
    if not name:
        raise CollectionError("VALIDATION_ERROR", "the collection needs a name")
    if len(name) > MAX_NAME:
        raise CollectionError("VALIDATION_ERROR", f"the name has at most {MAX_NAME} characters")
    return name


def _own(repo, uid, collection_id):
    row = repo.db.execute("SELECT * FROM saved_collections WHERE id=? AND user_id=?", (collection_id, uid)).fetchone()
    if not row:
        from .product_backend import not_found
        raise not_found("collection not found")
    return row


def list_collections(repo, uid):
    """Every collection with its story count and the picture of its newest story (the cover)."""
    out = []
    for row in repo.db.execute("SELECT * FROM saved_collections WHERE user_id=? ORDER BY position,created_at", (uid,)).fetchall():
        stories = repo.db.execute("""SELECT s.story_json FROM saved_collection_items i JOIN saved_stories s ON s.user_id=i.user_id AND s.story_id=i.story_id
            WHERE i.collection_id=? ORDER BY i.added_at DESC""", (row["id"],)).fetchall()
        cover = None
        for story in stories:
            cover = json.loads(story["story_json"]).get("image_url")
            if cover:
                break
        out.append({"id": row["id"], "name": row["name"], "count": len(stories), "cover_image_url": cover, "created_at": row["created_at"]})
    return out


def collections_of_story(repo, uid, story_id):
    return [row[0] for row in repo.db.execute("SELECT collection_id FROM saved_collection_items WHERE user_id=? AND story_id=?", (uid, story_id))]


def create_collection(repo, uid, data):
    from .subscriptions import PremiumRequired, limit, require
    require(repo, uid, "collections")
    name = _name((data or {}).get("name"))
    count = repo.db.execute("SELECT COUNT(*) FROM saved_collections WHERE user_id=?", (uid,)).fetchone()[0]
    if count >= limit(repo, uid, "collections"):
        raise PremiumRequired("collections", "collection limit reached")
    if repo.db.execute("SELECT 1 FROM saved_collections WHERE user_id=? AND lower(name)=lower(?)", (uid, name)).fetchone():
        raise CollectionError("COLLECTION_EXISTS", "there is already a collection with this name")
    collection_id = "collection_" + uuid.uuid4().hex
    repo.db.execute("INSERT INTO saved_collections(id,user_id,name,position,created_at,updated_at) VALUES(?,?,?,?,?,?)",
                    (collection_id, uid, name, count, now_iso(), now_iso()))
    repo.db.commit()
    return next(item for item in list_collections(repo, uid) if item["id"] == collection_id)


def rename_collection(repo, uid, collection_id, data):
    _own(repo, uid, collection_id)
    name = _name((data or {}).get("name"))
    repo.db.execute("UPDATE saved_collections SET name=?,updated_at=? WHERE id=?", (name, now_iso(), collection_id))
    repo.db.commit()
    return next(item for item in list_collections(repo, uid) if item["id"] == collection_id)


def delete_collection(repo, uid, collection_id):
    """The collection goes; its stories stay in Salvos."""
    _own(repo, uid, collection_id)
    repo.db.execute("DELETE FROM saved_collection_items WHERE collection_id=?", (collection_id,))
    repo.db.execute("DELETE FROM saved_collections WHERE id=?", (collection_id,))
    repo.db.commit()


def set_membership(repo, uid, collection_id, data):
    """Put a story in a collection (saving it first when ``story`` is sent) or take it out: ``{story_id|story, member}``."""
    from .subscriptions import require
    _own(repo, uid, collection_id)
    data = data or {}
    member = data.get("member", True)
    if not isinstance(member, bool):
        raise CollectionError("VALIDATION_ERROR", "member must be true or false")
    story_id = data.get("story_id") or (data.get("story") or {}).get("id")
    if not isinstance(story_id, str) or not story_id:
        raise CollectionError("VALIDATION_ERROR", "story_id is required")
    if member:
        require(repo, uid, "collections")
        if not repo.db.execute("SELECT 1 FROM saved_stories WHERE user_id=? AND story_id=?", (uid, story_id)).fetchone():
            if not isinstance(data.get("story"), dict):
                raise CollectionError("STORY_NOT_SAVED", "save the story first or send it")
            repo.save_story(uid, data["story"])
        repo.db.execute("INSERT INTO saved_collection_items(collection_id,user_id,story_id,added_at) VALUES(?,?,?,?) ON CONFLICT DO NOTHING",
                        (collection_id, uid, story_id, now_iso()))
    else:
        repo.db.execute("DELETE FROM saved_collection_items WHERE collection_id=? AND story_id=?", (collection_id, story_id))
    repo.db.commit()
    return {"collection_id": collection_id, "story_id": story_id, "member": member, "collections": collections_of_story(repo, uid, story_id)}


def collection_stories(repo, uid, collection_id):
    _own(repo, uid, collection_id)
    rows = repo.db.execute(repo._SAVED_SELECT.replace("WHERE s.user_id=?", "JOIN saved_collection_items i ON i.user_id=s.user_id AND i.story_id=s.story_id WHERE s.user_id=? AND i.collection_id=?"),
                           (uid, collection_id)).fetchall()
    return {"items": [repo._saved_row(row) for row in rows]}
