"""SQLite-backed agricultural graph store.

This is a real persistent graph store with nodes/edges tables. It is not a
recommendation engine. Every edge is reference-only unless a separate agronomic
engine and human review convert a recommendation downstream.

The store is a **global, non-tenant agricultural reference store only** (owner
decision on #1472, 14 November 2026; ADR-0038). Its tables carry no tenant column
and every authenticated caller reads the same rows. Data specific to a tenant,
farm, field or user must therefore never enter it: ``upsert_node`` and
``upsert_edge`` refuse any record that carries such an identifier or is marked
private (``TenantScopedDataError``).
"""

from __future__ import annotations

import json
import re
import sqlite3
import unicodedata
from dataclasses import dataclass
from pathlib import Path
from typing import Any

SEED_REFERENCE_RELATIONS = (
    "historically_susceptible_to",
    "historically_favored_by",
    "historically_limits",
    "historically_used_for",
)


@dataclass(frozen=True)
class GraphNode:
    node_id: str
    label: str
    name: str
    properties: dict[str, Any] | None = None


@dataclass(frozen=True)
class GraphEdge:
    edge_id: str
    subject_id: str
    relation: str
    object_id: str
    confidence: str = "reference"
    prescriptive: bool = False
    properties: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        if self.prescriptive:
            raise ValueError("Knowledge graph edges must not be prescriptive")
        if self.confidence != "reference":
            raise ValueError("Knowledge graph confidence must be 'reference'")
        if self.relation in {"controls", "recommends", "prescribes"}:
            raise ValueError("Use reference relation names such as historically_used_for")


# ── #1472 / ADR-0038: the global-reference-only write guard ─────────────────────
#
# Keys are normalised (NFKC, case-folded) and split into tokens on ``_ - .``,
# whitespace and camelCase boundaries; plural tokens are reduced to the singular.
# So ``tenant_id``, ``tenantId``, ``TENANT-UUID``, ``tenants``, ``farm_ids`` and a
# full-width ``ｔｅｎａｎｔ_id`` all yield a ``tenant``/``farm`` token.

# A key holding any of these tokens binds the record to a tenant, farm, field, user
# or organisation and is refused.
SCOPE_TOKENS = frozenset(
    {
        "tenant",
        "farm",
        "farmer",
        "field",
        "plot",
        "parcel",
        "org",
        "organization",
        "organisation",
        "user",
        "owner",
        "account",
        "customer",
    }
)
# A key token glued to an identifier suffix (``tenantid``, ``farmuuid``) counts too.
_ID_SUFFIXES = ("id", "uuid", "key", "ref", "code")
# Token sequences that bind a record to a person.
SCOPE_TOKEN_SEQUENCES = frozenset({("created", "by"), ("updated", "by"), ("owned", "by")})
# Keys that carry personal or location data: refused whatever the value.
PERSONAL_OR_LOCATION_TOKENS = frozenset(
    {"email", "geometry", "geom", "geojson", "polygon", "multipolygon", "wkt", "wkb"}
)
# Explicit allowlist of agronomic compounds whose first token is a scope word but
# that name reference concepts, not a scope. Matched as whole token pairs; nothing
# else is exempt. Tested in tests_v9/test_kg_global_reference_only.py.
AGRONOMIC_COMPOUNDS = frozenset(
    {
        ("field", "capacity"),  # soil water held after drainage
        ("field", "crop"),  # crop category (field crops vs horticulture)
        ("field", "pea"),  # Pisum sativum var. arvense
        ("field", "bean"),  # Vicia faba
        ("farm", "gate"),  # farm-gate price, a market reference
    }
)
# Visibility keys: only these values mean global; anything else is private.
VISIBILITY_KEYS = frozenset({"visibility", "scope", "access"})
GLOBAL_VISIBILITY = frozenset({"global", "public"})
# Keys that mark a record private when their value is true.
PRIVATE_FLAG_KEYS = frozenset({("private",), ("is", "private")})
_FALSE_STRINGS = frozenset({"false", "no", "0", "off", "n", ""})

# Identifier values (node_id, edge_id, subject_id, object_id, label, name,
# relation). A token from the strict set followed by anything is a scope id
# (``tenant-acme``, ``org:7``). A token from the ambiguous set, which is also
# agronomic vocabulary, is a scope id only when followed by ``: / = # @`` or by a
# token containing a digit (``field:7``, ``farm-12``). A bare label ``Field`` or a
# reference id ``field_crops`` stays allowed.
STRICT_ID_SCOPE_TOKENS = frozenset(
    {
        "tenant",
        "org",
        "organization",
        "organisation",
        "user",
        "owner",
        "account",
        "customer",
        "farmer",
    }
)
AMBIGUOUS_ID_SCOPE_TOKENS = frozenset({"farm", "field", "plot", "parcel"})
IDENTIFIER_FIELDS = ("node_id", "edge_id", "subject_id", "object_id", "label", "name", "relation")

TENANT_SCOPED_DATA_ERROR = "kg_tenant_scoped_data_forbidden"


class TenantScopedDataError(Exception):
    """A write carried tenant, farm, field or user data into the global graph.

    ``code`` is the stable machine token the API returns; ``path`` names the
    offending key (for example ``properties.metadata.field_id``). Deliberately not
    a ``ValueError``, so no generic handler can map it to something else.
    """

    def __init__(self, path: str, reason: str) -> None:
        self.code = TENANT_SCOPED_DATA_ERROR
        self.path = path
        self.reason = reason
        super().__init__(f"{TENANT_SCOPED_DATA_ERROR}: {reason} at {path!r}")


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])")
_KEY_SPLIT = re.compile(r"[\s_\-.]+")
_VALUE_SPLIT = re.compile(r"([:/=#@|,;\s_\-.]+)")
_STRONG_SEPARATOR = re.compile(r"[:/=#@]")


def _singular(token: str) -> str:
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _tokens(text: str) -> list[str]:
    text = unicodedata.normalize("NFKC", str(text))
    text = _CAMEL_BOUNDARY.sub("_", text)
    return [_singular(t.casefold()) for t in _KEY_SPLIT.split(text) if t]


def _drop_agronomic_compounds(tokens: list[str]) -> list[str]:
    out: list[str] = []
    i = 0
    while i < len(tokens):
        if i + 1 < len(tokens) and (tokens[i], tokens[i + 1]) in AGRONOMIC_COMPOUNDS:
            i += 2
            continue
        out.append(tokens[i])
        i += 1
    return out


def _is_scope_token(token: str) -> bool:
    if token in SCOPE_TOKENS:
        return True
    for base in SCOPE_TOKENS:
        for suffix in _ID_SUFFIXES:
            if token in (base + suffix, base + suffix + "s"):
                return True
    return False


def key_scope_reason(key: object) -> str | None:
    """Why ``key`` may not appear in the global graph, or ``None`` if it may."""
    tokens = _tokens(str(key))
    if tuple(tokens) in PRIVATE_FLAG_KEYS or (len(tokens) == 1 and tokens[0] in VISIBILITY_KEYS):
        return None  # decided on the value, see _value_reason
    for a, b in zip(tokens, tokens[1:], strict=False):
        if (a, b) in SCOPE_TOKEN_SEQUENCES:
            return "scope identifier key"
    for token in tokens:
        if token in PERSONAL_OR_LOCATION_TOKENS:
            return "personal or location data key"
    if any(_is_scope_token(t) for t in _drop_agronomic_compounds(tokens)):
        return "scope identifier key"
    return None


def _value_reason(key: object, value: Any) -> str | None:
    tokens = tuple(_tokens(str(key)))
    if tokens in PRIVATE_FLAG_KEYS:
        if isinstance(value, str):
            return None if value.strip().casefold() in _FALSE_STRINGS else "record marked private"
        return "record marked private" if value else None
    if len(tokens) == 1 and tokens[0] in VISIBILITY_KEYS:
        if isinstance(value, str) and value.strip().casefold() in GLOBAL_VISIBILITY:
            return None
        return "non-global visibility"
    return None


def identifier_scope_reason(value: object) -> str | None:
    """Why an id, label or name encodes a tenant/farm/field scope, or ``None``."""
    if not isinstance(value, str):
        return None
    text = unicodedata.normalize("NFKC", value)
    parts = _VALUE_SPLIT.split(_CAMEL_BOUNDARY.sub("_", text))
    # parts alternates token, separator, token, ...
    tokens = [
        (parts[i], parts[i + 1] if i + 1 < len(parts) else "") for i in range(0, len(parts), 2)
    ]
    tokens = [(_singular(t.casefold()), sep) for t, sep in tokens if t]
    for index, (token, sep) in enumerate(tokens):
        nxt = tokens[index + 1][0] if index + 1 < len(tokens) else None
        if nxt is None:
            continue
        if (token, nxt) in AGRONOMIC_COMPOUNDS:
            continue
        if token in STRICT_ID_SCOPE_TOKENS or any(
            token == base + suffix for base in STRICT_ID_SCOPE_TOKENS for suffix in _ID_SUFFIXES
        ):
            return "scope identifier in id or label"
        if token in AMBIGUOUS_ID_SCOPE_TOKENS and (
            _STRONG_SEPARATOR.search(sep) or any(ch.isdigit() for ch in nxt)
        ):
            return "scope identifier in id or label"
    return None


def _maybe_json(value: str) -> Any:
    stripped = value.strip()
    if not stripped or stripped[0] not in "{[":
        return None
    try:
        return json.loads(stripped)
    except ValueError:
        return None


def assert_global_reference_payload(payload: Any, path: str = "") -> None:
    """Refuse a payload that carries tenant/farm/field/user scope or a private mark.

    Walks nested mappings and lists, and string values that hold a JSON object or
    array, so a key hidden in ``properties``, ``properties.metadata`` or an encoded
    blob is found as well as one at the top level. A scope key is refused whatever
    its value, including ``None``: the key itself declares a scope this store does
    not have.
    """
    if isinstance(payload, dict):
        for key, value in payload.items():
            here = f"{path}.{key}" if path else str(key)
            reason = key_scope_reason(key) or _value_reason(key, value)
            if reason:
                raise TenantScopedDataError(here, reason)
            assert_global_reference_payload(value, here)
    elif isinstance(payload, (list, tuple)):
        for index, item in enumerate(payload):
            assert_global_reference_payload(item, f"{path}[{index}]")
    elif isinstance(payload, str):
        decoded = _maybe_json(payload)
        if decoded is not None:
            assert_global_reference_payload(decoded, f"{path}<json>")


def assert_global_reference_identifiers(record: Any) -> None:
    """Refuse a node or edge whose id, label, name or relation encodes a scope."""
    for field_name in IDENTIFIER_FIELDS:
        value = getattr(record, field_name, None)
        reason = identifier_scope_reason(value)
        if reason:
            raise TenantScopedDataError(field_name, reason)


def assert_global_reference_record(record: Any) -> None:
    """The full #1472 check for a ``GraphNode`` or ``GraphEdge``."""
    assert_global_reference_identifiers(record)
    assert_global_reference_payload(record.properties or {}, "properties")


class EdgeConflictError(Exception):
    """An existing ``edge_id`` was re-posted with different endpoints.

    The upsert used to update only ``relation``/``properties_json`` and keep the old
    ``subject_id``/``object_id`` while reporting success, so the caller believed an edge
    existed that the graph did not hold. Endpoints are the edge's identity: changing them
    needs a new ``edge_id``, and the conflicting write is refused instead.
    """


class SQLiteAgGraphStore:
    def __init__(self, db_path: str | Path) -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_schema()

    def _connect(self) -> sqlite3.Connection:
        """اتّصالٌ **يفرض** المفاتيح الأجنبيّة — لأنّ الإعداد لكلّ اتّصالٍ على حدة.

        **العطلُ الذي وُجِد هذا لأجله (D12):** كان ``PRAGMA foreign_keys=ON`` يُنفَّذ في
        ``_init_schema`` وحدَه، و``_connect`` يُرجِع اتّصالاً بالافتراض ``OFF``. فكلُّ
        كتابةٍ بعد الإنشاء تقع **بلا فرضٍ للمفاتيح**، ووجودُ ``REFERENCES`` في الـDDL
        لا يكفي — وهذا منصوصٌ في توثيق SQLite: الإعدادُ لكلّ اتّصال.

        **والأثرُ رقمٌ يكذب:** علاقةٌ بين عقدتين غير موجودتين تُقبَل، فيُرجِع
        ``count_edges`` اثنتين بينما ``query_edges`` الموصولةُ بالعقد تُرجِع واحدة.
        مُقاسٌ بالتشغيل على SQLite حقيقيّة (3.45.1): ``foreign_keys=0`` · العلاقةُ
        اليتيمةُ قُبِلت · ``2`` مقابل ``1``.

        **والفرضُ يُتحقَّق منه لا يُفترَض:** ``PRAGMA foreign_keys`` قراءةٌ صامتة إن
        نُفِّذت داخل معاملةٍ مفتوحة، فالتأكيدُ هنا يجعل الفشلَ مرئيّاً عند الاتّصال
        بدل أن يظهر بياناتٍ يتيمةً بعد حين.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys=ON")
        if (
            conn.execute("PRAGMA foreign_keys").fetchone()[0] != 1
        ):  # pragma: no cover - بناءٌ بلا دعم
            conn.close()
            raise RuntimeError(
                "تعذّر فرضُ foreign_keys على اتّصال SQLite — نسخةٌ مبنيّةٌ بلا دعمٍ للمفاتيح "
                "الأجنبيّة. الكتابةُ بلا فرضٍ تقبل علاقاتٍ يتيمة، فيُرفَض الاتّصالُ بدل أن "
                "يُصمَت عنها."
            )
        return conn

    def _init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                """CREATE TABLE IF NOT EXISTS kg_nodes (
                    node_id TEXT PRIMARY KEY,
                    label TEXT NOT NULL,
                    name TEXT NOT NULL,
                    properties_json TEXT NOT NULL DEFAULT '{}'
                )"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS kg_edges (
                    edge_id TEXT PRIMARY KEY,
                    subject_id TEXT NOT NULL REFERENCES kg_nodes(node_id),
                    relation TEXT NOT NULL,
                    object_id TEXT NOT NULL REFERENCES kg_nodes(node_id),
                    confidence TEXT NOT NULL CHECK(confidence='reference'),
                    prescriptive INTEGER NOT NULL CHECK(prescriptive=0),
                    properties_json TEXT NOT NULL DEFAULT '{}'
                )"""
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_subject ON kg_edges(subject_id)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_kg_edges_relation ON kg_edges(relation)")

    def upsert_node(self, node: GraphNode) -> None:
        import json

        # #1472 write boundary: every node write passes here (REST, seeding).
        assert_global_reference_record(node)
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO kg_nodes(node_id,label,name,properties_json) VALUES(?,?,?,?) "
                "ON CONFLICT(node_id) DO UPDATE SET label=excluded.label,name=excluded.name,properties_json=excluded.properties_json",
                (
                    node.node_id,
                    node.label,
                    node.name,
                    json.dumps(node.properties or {}, ensure_ascii=False),
                ),
            )

    def upsert_edge(self, edge: GraphEdge) -> None:
        import json

        # #1472 write boundary: every edge write passes here (REST, seeding).
        assert_global_reference_record(edge)
        with self._connect() as conn:
            # The WHERE makes the conflict path a no-op when the stored endpoints differ;
            # rowcount 0 then means the edge_id is taken by another (subject, object).
            cursor = conn.execute(
                "INSERT INTO kg_edges(edge_id,subject_id,relation,object_id,confidence,prescriptive,properties_json) "
                "VALUES(?,?,?,?,?,?,?) ON CONFLICT(edge_id) DO UPDATE SET relation=excluded.relation,properties_json=excluded.properties_json "
                "WHERE kg_edges.subject_id=excluded.subject_id AND kg_edges.object_id=excluded.object_id",
                (
                    edge.edge_id,
                    edge.subject_id,
                    edge.relation,
                    edge.object_id,
                    edge.confidence,
                    0,
                    json.dumps(edge.properties or {}, ensure_ascii=False),
                ),
            )
            if cursor.rowcount == 0:
                raise EdgeConflictError(
                    f"edge_id {edge.edge_id!r} already links different endpoints; "
                    "use a new edge_id to connect other nodes"
                )

    def count_edges(self) -> int:
        with self._connect() as conn:
            return int(conn.execute("SELECT COUNT(*) FROM kg_edges").fetchone()[0])

    def query_edges(
        self,
        *,
        subject_id: str | None = None,
        relation: str | None = None,
        object_id: str | None = None,
    ) -> list[dict[str, Any]]:
        query = """
            SELECT e.edge_id,e.subject_id,s.name AS subject_name,e.relation,e.object_id,o.name AS object_name,
                   e.confidence,e.prescriptive,e.properties_json
            FROM kg_edges e
            JOIN kg_nodes s ON s.node_id=e.subject_id
            JOIN kg_nodes o ON o.node_id=e.object_id
            WHERE 1=1
        """
        params: list[Any] = []
        if subject_id:
            query += " AND e.subject_id=?"
            params.append(subject_id)
        if relation:
            query += " AND e.relation=?"
            params.append(relation)
        if object_id:
            query += " AND e.object_id=?"
            params.append(object_id)
        with self._connect() as conn:
            return [dict(row) for row in conn.execute(query, params).fetchall()]

    def graph_context_for_crop(self, crop_id: str) -> dict[str, Any]:
        return {
            "type": "kg_annotation",
            "verified": False,
            "decision_authority": "none",
            "edges": self.query_edges(subject_id=crop_id),
        }


def seed_reference_ontology(store: SQLiteAgGraphStore) -> int:
    if store.count_edges() > 0:
        return 0
    nodes = [
        GraphNode("wheat", "Crop", "Wheat"),
        GraphNode("stripe_rust", "Disease", "Stripe rust"),
        GraphNode("cool_humid_weather", "WeatherRisk", "Cool humid weather"),
        GraphNode("soil_ec", "SoilCondition", "Soil electrical conductivity"),
        GraphNode("salt_sensitive_crops", "CropGroup", "Salt-sensitive crops"),
        GraphNode(
            "fungicide_review_required",
            "Treatment",
            "Fungicide option requires agronomist review",
            {"requires_phi": True},
        ),
    ]
    for node in nodes:
        store.upsert_node(node)
    edges = [
        GraphEdge("e1", "wheat", SEED_REFERENCE_RELATIONS[0], "stripe_rust"),
        GraphEdge("e2", "stripe_rust", SEED_REFERENCE_RELATIONS[1], "cool_humid_weather"),
        GraphEdge("e3", "soil_ec", SEED_REFERENCE_RELATIONS[2], "salt_sensitive_crops"),
        GraphEdge(
            "e4",
            "fungicide_review_required",
            SEED_REFERENCE_RELATIONS[3],
            "stripe_rust",
            properties={"human_review_required": True},
        ),
    ]
    for edge in edges:
        store.upsert_edge(edge)
    return len(edges)


def graphql_readonly(store: SQLiteAgGraphStore, query: str) -> dict[str, Any]:
    """Dependency-free read-only GraphQL-like facade.

    Supports filters: subject:"wheat" relation:"historically_susceptible_to".
    Mutations are rejected explicitly.
    """
    lowered = query.lower()
    if "mutation" in lowered or "delete" in lowered or "update" in lowered:
        raise ValueError("Knowledge Graph GraphQL facade is read-only")
    subject = None
    relation = None
    if 'subject:"' in query:
        subject = query.split('subject:"', 1)[1].split('"', 1)[0]
    if 'relation:"' in query:
        relation = query.split('relation:"', 1)[1].split('"', 1)[0]
    return {"edges": store.query_edges(subject_id=subject, relation=relation)}


def scan_existing_rows(db_path: str | Path) -> list[dict[str, Any]]:
    """Report stored rows that violate the #1472 rule. Read-only; deletes nothing.

    The write guard only sees new writes. Rows already in ``/data/kg.sqlite`` from
    before it existed are checked here: the database is opened with
    ``mode=ro``, every node and edge is passed through the same checks, and each
    violation is returned as ``{"table", "id", "path", "reason"}``.
    """
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    findings: list[dict[str, Any]] = []
    conn = sqlite3.connect(uri, uri=True)
    try:
        conn.row_factory = sqlite3.Row
        for table, id_col in (("kg_nodes", "node_id"), ("kg_edges", "edge_id")):
            for row in conn.execute(f"SELECT * FROM {table}"):  # noqa: S608 - fixed names
                data = dict(row)
                try:
                    props = json.loads(data.pop("properties_json") or "{}")
                except ValueError:
                    props = data.get("properties_json")
                fields = {k: v for k, v in data.items() if k in IDENTIFIER_FIELDS}
                record = type("StoredRow", (), {**fields, "properties": props})()
                try:
                    assert_global_reference_record(record)
                except TenantScopedDataError as exc:
                    findings.append(
                        {"table": table, "id": data[id_col], "path": exc.path, "reason": exc.reason}
                    )
    finally:
        conn.close()
    return findings


def _main(argv: list[str] | None = None) -> int:
    """``python -m kg_store --scan [DB]``: print violations as JSON; exit 1 if any."""
    import argparse
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--scan", nargs="?", const=os.getenv("KG_SQLITE_PATH", "/data/kg.sqlite"))
    args = parser.parse_args(argv)
    if not args.scan:
        parser.error("--scan [DB] is the only action")
    findings = scan_existing_rows(args.scan)
    print(json.dumps({"db": str(args.scan), "violations": findings}, ensure_ascii=False, indent=2))
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(_main())
