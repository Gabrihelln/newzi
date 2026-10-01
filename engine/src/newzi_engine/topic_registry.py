"""Canonical, data-driven taxonomy shared by the engine and product API."""
import json
import unicodedata
from functools import lru_cache
from pathlib import Path

from .paths import ENGINE_CONFIG

REGISTRY_PATH = ENGINE_CONFIG / "taxonomy.json"


def _normalized(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    return "".join(character for character in value if not unicodedata.combining(character)).casefold().strip().replace("_", "-")


class Taxonomy:
    def __init__(self, nodes):
        self.nodes = {node["id"]: dict(node) for node in nodes}
        self.aliases = {}
        for node in self.nodes.values():
            for value in (node["id"], node.get("slug"), node.get("name"), *node.get("aliases", [])):
                key = _normalized(value)
                if key in self.aliases and self.aliases[key] != node["id"]:
                    raise ValueError(f"ambiguous taxonomy alias: {value}")
                self.aliases[key] = node["id"]
            parent = node.get("parent_id")
            if parent and parent not in self.nodes:
                raise ValueError(f"unknown taxonomy parent: {parent}")
        for node_id in self.nodes:
            seen = set()
            current = node_id
            while current:
                if current in seen:
                    raise ValueError(f"taxonomy cycle: {node_id}")
                seen.add(current)
                current = self.nodes[current].get("parent_id")
        self._ancestors = {}
        for node_id in self.nodes:
            chain = []
            current = self.nodes[node_id].get("parent_id")
            while current:
                chain.append(current)
                current = self.nodes[current].get("parent_id")
            self._ancestors[node_id] = tuple(chain)
        descendants = {node_id: [] for node_id in self.nodes}
        for node_id, chain in self._ancestors.items():
            for ancestor in chain:
                descendants[ancestor].append(node_id)
        self._descendants = {node_id: tuple(children) for node_id, children in descendants.items()}
        for node_id, node in self.nodes.items():
            node["depth"] = len(self._ancestors[node_id])
            node["path"] = [*reversed(self._ancestors[node_id]), node_id]
            node["children"] = [candidate for candidate in self.nodes if self.nodes[candidate].get("parent_id") == node_id]

    @classmethod
    def load(cls, path=None):
        return cls(json.loads(Path(path or REGISTRY_PATH).read_text(encoding="utf-8"))["nodes"])

    def resolve(self, value, active_only=True):
        node_id = self.aliases.get(_normalized(value))
        return node_id if node_id and (not active_only or self.nodes[node_id].get("active", True)) else None

    def canonicalize(self, values):
        resolved, unknown = set(), []
        for value in values or []:
            node_id = self.resolve(value)
            if node_id:
                resolved.add(node_id)
            else:
                unknown.append(value)
        return tuple(sorted(resolved)), unknown

    def ancestors(self, node_id):
        return list(self._ancestors.get(node_id, ()))

    def descendants(self, node_id):
        return list(self._descendants.get(node_id, ()))

    def rows(self):
        return [{"id": n["id"], "code": n["id"], "slug": n.get("slug"), "label": n["name"], "name": n["name"], "description": n.get("description", ""), "aliases": list(n.get("aliases", [])), "parent_id": n.get("parent_id"), "depth": n["depth"], "path": list(n["path"]), "children": list(n["children"]), "type": n.get("type", "subject"), "enabled": bool(n.get("active", True)), "order": n.get("display_order", 0)} for n in sorted(self.nodes.values(), key=lambda x: x.get("display_order", 0))]


@lru_cache(maxsize=4)
def _cached_taxonomy(path, modified):
    return Taxonomy.load(path)


def taxonomy():
    # A changed data file becomes visible without changing or restarting engine code.
    return _cached_taxonomy(str(REGISTRY_PATH), REGISTRY_PATH.stat().st_mtime_ns)


_INITIAL = taxonomy()
TOPIC_REGISTRY = [(n["id"], n["name"], n.get("description", "")) for n in _INITIAL.nodes.values()]
TOPIC_IDS = tuple(_INITIAL.nodes)
TOPIC_LABELS = {n["id"]: n["name"] for n in _INITIAL.nodes.values()}
SUPPORTED_TOPIC_IDS = frozenset(n["id"] for n in _INITIAL.nodes.values() if n.get("active", True))


def topic_rows():
    return taxonomy().rows()
