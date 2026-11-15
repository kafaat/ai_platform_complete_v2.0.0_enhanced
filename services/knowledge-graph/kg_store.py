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
# The rule refuses what is *shaped like* a scope identifier, not every key that
# contains a scope word: ``farm_id`` and ``owner`` are refused, ``farm_size_ha`` and
# ``data_owner`` are reference properties and pass. ADR-0038 lists what is and is
# not enforced.

# Scope words (English and Arabic). Matched as whole normalised tokens; English
# plurals are reduced to the singular and the Arabic article ``ال`` is removed.
SCOPE_WORDS = frozenset(
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
        "grower",
        "holding",
        "site",
        "company",
        "client",
        "member",
        "person",
        "landlord",
        "مستأجر",
        "مزرعة",
        "مزارع",
        "حقل",
        "قطعة",
        "مالك",
        "مستخدم",
        "منظمة",
        "عميل",
    }
)
# A scope word immediately followed by one of these is an identifier key.
ID_SUFFIXES = frozenset({"id", "ids", "uuid", "key", "ref", "code", "no", "number", "name"})
# Arabic puts the identifier word first: معرف_المزرعة, رقم_الحقل.
ARABIC_ID_WORDS = frozenset({"معرف", "رقم", "رمز", "اسم", "هوية"})
# Personal or location data. Any of these tokens anywhere in a key refuses it.
PERSONAL_TOKENS = frozenset(
    {"email", "phone", "geometry", "geojson", "coordinates", "latitude", "longitude", "address"}
)
# Personal or location keys refused when they are the whole key.
PERSONAL_KEYS = frozenset(
    {
        ("location",),
        ("lat",),
        ("lon",),
        ("lng",),
        ("boundary",),
        ("author",),
        ("geo", "point"),
        ("created", "by"),
        ("submitted", "by"),
        ("updated", "by"),
        ("owned", "by"),
    }
)
GEOJSON_TYPES = frozenset(
    {
        "Point",
        "MultiPoint",
        "LineString",
        "MultiLineString",
        "Polygon",
        "MultiPolygon",
        "GeometryCollection",
        "Feature",
        "FeatureCollection",
    }
)
# Visibility: a key with one of these tokens refuses an explicit private marker.
VISIBILITY_TOKENS = frozenset(
    {"visibility", "privacy", "access", "scope", "sharing", "audience", "acl", "shared", "public"}
)
PRIVATE_MARKERS = frozenset(
    {"private", "restricted", "organization", "organisation", "tenant", "internal"}
)
_FALSE_STRINGS = frozenset({"false", "no", "0", "off", "n", ""})
# Ids, labels and names: separators that bind a scope word to an identifier.
_ID_AFTER_SCOPE = frozenset({":", "#", "/", "-"})  # <scope>[:#/-]<token>
_ID_BEFORE_SCOPE = frozenset({":", "-"})  # <token>[:-]<scope>
_VALUE_ID_SUFFIXES = frozenset({"id", "ids", "uuid", "key", "ref", "code"})
IDENTIFIER_FIELDS = ("node_id", "edge_id", "subject_id", "object_id", "label", "name", "relation")

# Robustness limits: the guard must answer 4xx, never 500 or a long stall.
MAX_PAYLOAD_DEPTH = 64
MAX_PAYLOAD_ITEMS = 10_000

TENANT_SCOPED_DATA_ERROR = "kg_tenant_scoped_data_forbidden"
PAYLOAD_TOO_DEEP_ERROR = "kg_payload_too_deep"
PAYLOAD_TOO_LARGE_ERROR = "kg_payload_too_large"


class GraphWriteRefused(Exception):
    """Base for refused graph writes: a stable ``code``, a ``path`` and an HTTP status."""

    status = 422

    def __init__(self, code: str, path: str, reason: str) -> None:
        self.code = code
        self.path = path
        self.reason = reason
        super().__init__(f"{code}: {reason} at {path!r}")


class TenantScopedDataError(GraphWriteRefused):
    """A write carried tenant, farm, field or user data into the global graph.

    Deliberately not a ``ValueError``, so no generic handler can map it elsewhere.
    """

    def __init__(self, path: str, reason: str) -> None:
        super().__init__(TENANT_SCOPED_DATA_ERROR, path, reason)


class PayloadLimitError(GraphWriteRefused):
    """The payload is too deep (422) or has too many items (413) to check."""

    def __init__(self, code: str, path: str, reason: str, status: int) -> None:
        super().__init__(code, path, reason)
        self.status = status


# Confusables: Latin look-alikes mapped to their ASCII skeleton (Cyrillic, Greek,
# dotless i). Small and explicit; other scripts are out of scope (ADR-0038).
_CONFUSABLES = str.maketrans(
    {
        "а": "a",
        "е": "e",
        "о": "o",
        "р": "p",
        "с": "c",
        "у": "y",
        "х": "x",
        "і": "i",
        "ј": "j",
        "ѕ": "s",
        "А": "A",
        "Е": "E",
        "О": "O",
        "Р": "P",
        "С": "C",
        "Т": "T",
        "Х": "X",
        "І": "I",
        "ı": "i",
        "ο": "o",
        "α": "a",
        "ρ": "p",
        "ν": "v",
        "Ο": "O",
        "Α": "A",
    }
)
_ARABIC_MARKS = re.compile("[ً-ٰٟـ]")
_BOUNDARY = re.compile(
    r"(?<=[a-z])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])|(?<=[^\W\d_])(?=\d)|(?<=\d)(?=[^\W\d_])"
)


def _clean_text(text: str) -> str:
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    text = text.translate(_CONFUSABLES)
    return _ARABIC_MARKS.sub("", text)


def _segments(text: object) -> list[tuple[str, str]]:
    """Normalised ``(token, separator_after)`` pairs; glued boundaries give ``""``."""
    cleaned = _BOUNDARY.sub("\x00", _clean_text(str(text)))
    out: list[tuple[str, str]] = []
    pos = 0
    for match in re.finditer(r"[\x00\s_\-.:/#@=,;|]+", cleaned):
        token = cleaned[pos : match.start()]
        if token:
            out.append((token.casefold(), match.group().replace("\x00", "")))
        pos = match.end()
    if cleaned[pos:]:
        out.append((cleaned[pos:].casefold(), ""))
    return out


def _tokens(text: object) -> list[str]:
    return [token for token, _ in _segments(text)]


def _base(token: str) -> str:
    """Singular English token, or an Arabic token without its article."""
    if token.startswith("ال") and len(token) > 3:
        return token[2:]
    if len(token) > 4 and token.endswith("ies"):
        return token[:-3] + "y"
    if len(token) > 3 and token.endswith("s") and not token.endswith("ss"):
        return token[:-1]
    return token


def _is_scope(token: str) -> bool:
    return token in SCOPE_WORDS or _base(token) in SCOPE_WORDS


def _glued_scope_id(token: str) -> bool:
    # ``farmname``, ``tenantid`` written without any boundary.
    return any(
        token.startswith(word) and _base(token[len(word) :]) in ID_SUFFIXES
        for word in SCOPE_WORDS
        if word.isascii()
    )


def key_scope_reason(key: object) -> str | None:
    """Why ``key`` may not appear in the global graph, or ``None`` if it may."""
    tokens = _tokens(key)
    if not tokens:
        return None
    if len(tokens) == 1 and (_is_scope(tokens[0]) or _glued_scope_id(tokens[0])):
        return "scope identifier key"
    for a, b in zip(tokens, tokens[1:], strict=False):
        if _is_scope(a) and (b in ID_SUFFIXES or _base(b) in ID_SUFFIXES):
            return "scope identifier key"
        if a in ARABIC_ID_WORDS and _is_scope(b):
            return "scope identifier key"
        if _is_scope(a) and b in ARABIC_ID_WORDS:
            return "scope identifier key"
    if any(_glued_scope_id(t) for t in tokens):
        return "scope identifier key"
    if any(t in PERSONAL_TOKENS for t in tokens) or tuple(tokens) in PERSONAL_KEYS:
        return "personal or location data key"
    return None


def _is_false(value: Any) -> bool:
    if isinstance(value, str):
        return value.strip().casefold() in _FALSE_STRINGS
    return not value


def _is_private_marker(value: Any) -> bool:
    if isinstance(value, str):
        return _clean_text(value).strip().casefold() in PRIVATE_MARKERS
    if isinstance(value, (list, tuple)):
        return any(_is_private_marker(v) for v in value)
    return False


def visibility_reason(key: object, value: Any) -> str | None:
    """Why ``key: value`` marks the record private, or ``None``."""
    tokens = _tokens(key)
    if tokens in (["private"], ["is", "private"]):
        return None if _is_false(value) else "record marked private"
    if not any(t in VISIBILITY_TOKENS for t in tokens):
        return None
    if tokens in (["public"], ["is", "public"]) and not isinstance(value, (dict, list)):
        return "record marked not public" if _is_false(value) else None
    if tokens[-2:] == ["shared", "with"] and value not in (None, "", [], {}):
        return "record shared with a scope"
    if _is_private_marker(value):
        return "non-global visibility"
    return None


def identifier_scope_reason(value: object) -> str | None:
    """Why an id, label or name encodes a tenant/farm/field scope, or ``None``.

    Refused: ``<scope>[:#/-]<token>`` (``tenant:acme``, ``farm-12``),
    ``<token>[:-]<scope>`` (``acme-tenant``, ``7:field``), a scope word glued to a
    digit run (``farm12``, ``12field``) and a scope word followed by an id suffix
    (``customerId42``). Prose (``Farmer field schools``) and reference ids joined
    by ``_`` (``plot_2x2_design``) pass.
    """
    if not isinstance(value, str):
        return None
    segs = _segments(value)
    for i, (token, sep) in enumerate(segs):
        nxt = segs[i + 1][0] if i + 1 < len(segs) else None
        if nxt is None:
            continue
        if _is_scope(token) and sep in _ID_AFTER_SCOPE:
            return "scope identifier in id or label"
        if _is_scope(nxt) and sep in _ID_BEFORE_SCOPE:
            return "scope identifier in id or label"
        if sep == "" and (
            (_is_scope(token) and nxt.isdigit()) or (token.isdigit() and _is_scope(nxt))
        ):
            return "scope identifier in id or label"
        if _is_scope(token) and nxt in _VALUE_ID_SUFFIXES and sep in {"", "_", "-"}:
            return "scope identifier in id or label"
    return None


def _decode_json_text(value: str, path: str) -> Any:
    """Decode a string that holds JSON (BOM and one string-literal layer allowed)."""
    for _ in range(2):
        stripped = value.lstrip("\ufeff").strip()
        if not stripped or stripped[0] not in '{["':
            return None
        try:
            decoded = json.loads(stripped)
        except RecursionError as exc:
            raise PayloadLimitError(
                PAYLOAD_TOO_DEEP_ERROR, path, "nesting too deep to check", 422
            ) from exc
        except ValueError:
            return None
        if not isinstance(decoded, str):
            return decoded
        value = decoded
    return None


def assert_global_reference_payload(payload: Any, path: str = "") -> None:
    """Refuse a payload that carries tenant/farm/field/user scope or a private mark.

    Walks nested mappings and lists, and string values that hold JSON, so a key in
    ``properties``, ``properties.metadata`` or an encoded blob is found as well as
    one at the top level. Depth is capped at ``MAX_PAYLOAD_DEPTH`` (422) and the
    number of keys and items at ``MAX_PAYLOAD_ITEMS`` (413).
    """
    budget = [MAX_PAYLOAD_ITEMS]

    def walk(node: Any, here: str, depth: int) -> None:
        if depth > MAX_PAYLOAD_DEPTH:
            raise PayloadLimitError(
                PAYLOAD_TOO_DEEP_ERROR, here, f"nesting deeper than {MAX_PAYLOAD_DEPTH}", 422
            )
        if isinstance(node, dict):
            if node.get("type") in GEOJSON_TYPES:
                raise TenantScopedDataError(here or "<root>", "GeoJSON location value")
            for key, value in node.items():
                budget[0] -= 1
                if budget[0] < 0:
                    raise PayloadLimitError(
                        PAYLOAD_TOO_LARGE_ERROR, here, f"more than {MAX_PAYLOAD_ITEMS} items", 413
                    )
                child = f"{here}.{key}" if here else str(key)
                reason = key_scope_reason(key) or visibility_reason(key, value)
                if reason:
                    raise TenantScopedDataError(child, reason)
                walk(value, child, depth + 1)
        elif isinstance(node, (list, tuple)):
            for index, item in enumerate(node):
                budget[0] -= 1
                if budget[0] < 0:
                    raise PayloadLimitError(
                        PAYLOAD_TOO_LARGE_ERROR, here, f"more than {MAX_PAYLOAD_ITEMS} items", 413
                    )
                walk(item, f"{here}[{index}]", depth + 1)
        elif isinstance(node, str):
            decoded = _decode_json_text(node, here)
            if decoded is not None:
                walk(decoded, f"{here}<json>", depth + 1)

    walk(payload, path, 0)


def assert_global_reference_identifiers(record: Any) -> None:
    """Refuse a node or edge whose id, label, name or relation encodes a scope."""
    for field_name in IDENTIFIER_FIELDS:
        reason = identifier_scope_reason(getattr(record, field_name, None))
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


def open_readonly(db_path: str | Path) -> sqlite3.Connection:
    """A connection that SQLite itself refuses to write through (``mode=ro``)."""
    uri = f"{Path(db_path).resolve().as_uri()}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def scan_existing_rows(db_path: str | Path) -> list[dict[str, Any]]:
    """Report stored rows that violate the #1472 rule. Read-only; deletes nothing.

    The write guard only sees new writes. Rows already in ``/data/kg.sqlite`` from
    before it existed are checked here through ``open_readonly``: every node and
    edge goes through the same checks, and a row whose ``properties_json`` is not
    valid JSON is reported too. Each finding is ``{"table", "id", "path", "reason"}``.
    """
    findings: list[dict[str, Any]] = []
    conn = open_readonly(db_path)
    try:
        for table, id_col in (("kg_nodes", "node_id"), ("kg_edges", "edge_id")):
            for row in conn.execute(f"SELECT * FROM {table}"):  # noqa: S608 - fixed names
                data = dict(row)
                raw = data.pop("properties_json")
                try:
                    props = json.loads(raw or "{}")
                except ValueError:
                    findings.append(
                        {
                            "table": table,
                            "id": data[id_col],
                            "path": "properties_json",
                            "reason": "properties_json is not valid JSON",
                        }
                    )
                    props = {}
                fields = {k: v for k, v in data.items() if k in IDENTIFIER_FIELDS}
                record = type("StoredRow", (), {**fields, "properties": props})()
                try:
                    assert_global_reference_record(record)
                except GraphWriteRefused as exc:
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
