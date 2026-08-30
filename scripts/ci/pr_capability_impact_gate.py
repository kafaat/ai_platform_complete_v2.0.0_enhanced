#!/usr/bin/env python3
"""Compute and enforce pull-request capability impact declarations.

The gate uses both current and merge-base snapshots so deletions and renames cannot
escape impact detection after generated evidence is refreshed on the PR branch.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
from collections import defaultdict, deque
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

import yaml

ROOT = Path(__file__).resolve().parents[2]
REGISTRY_PATH = Path("docs/capability-registry/generated/capability_registry.json")
MAPPING_PATH = Path("docs/capability-registry/generated/mapping/capability_mapping.json")
ROADMAP_PATH = Path("docs/capability-registry/roadmap/roadmap_items.yaml")
ROADMAP_LINKER_PATH = Path("scripts/ci/capability_roadmap_linker.py")
GATE_PATH = Path("scripts/ci/pr_capability_impact_gate.py")
LEGACY_IMPACT_PATH = Path("scripts/ci/capability_impact.py")
WORKFLOW_PATH = Path(".github/workflows/capability-governance.yml")
OUTPUT_DIR = ROOT / "docs/capability-registry/generated/impact"
INDEX_SUMMARY_PATH = OUTPUT_DIR / "impact_index_summary.json"
SCHEMA_VERSION = "2.0.0"
CAPABILITY_ID_RE = re.compile(r"^[A-Z][A-Z0-9]*-\d{3}$")
LINE_SUFFIX_RE = re.compile(r":\d+(?::\d+)?$")
DECLARATION_RE = re.compile(r"(?im)^Capability-Impact:\s*(.*?)\s*$")
MAPPING_DIMENSIONS = (
    "backend",
    "routes",
    "database",
    "events",
    "web",
    "mobile",
    "tests",
    "governance",
    "other_evidence",
)


@dataclass
class Reference:
    capabilities: set[str] = field(default_factory=set)
    sources: set[str] = field(default_factory=set)
    recursive: bool = False
    governance_wide: bool = False


@dataclass
class Snapshot:
    references: dict[str, Reference]
    dependents: dict[str, set[str]]
    known_capabilities: set[str]
    input_hashes: dict[str, str]


def sha256_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def normalize_repo_path(raw: Any) -> str:
    value = str(raw or "").strip()
    if " @ " in value:
        value = value.rsplit(" @ ", 1)[1]
    value = LINE_SUFFIX_RE.sub("", value.replace("\\", "/").strip())
    while value.startswith("./"):
        value = value[2:]
    if not value:
        raise ValueError("empty repository path")
    path = PurePosixPath(value)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"path must stay inside the repository: {raw!r}")
    normalized = path.as_posix()
    if normalized in {"", "."}:
        raise ValueError(f"invalid repository path: {raw!r}")
    return normalized


def extract_repository_path(value: Any) -> str | None:
    candidate: Any = value
    if isinstance(value, dict):
        candidate = value.get("path")
        if candidate is None:
            candidate = value.get("value")
    if not isinstance(candidate, str) or not candidate.strip():
        return None
    if " @ " in candidate:
        candidate = candidate.rsplit(" @ ", 1)[1]
    elif "/" not in candidate and "\\" not in candidate:
        return None
    try:
        return normalize_repo_path(candidate)
    except ValueError:
        return None


def add_reference(
    references: dict[str, Reference],
    raw_path: Any,
    capability_ids: Iterable[str],
    *,
    source: str,
    recursive: bool = False,
    governance_wide: bool = False,
) -> None:
    try:
        path = normalize_repo_path(raw_path)
    except ValueError:
        return
    capability_set = {capability_id for capability_id in capability_ids if capability_id}
    if not capability_set:
        return
    ref = references.setdefault(path, Reference())
    ref.capabilities.update(capability_set)
    ref.sources.add(source)
    ref.recursive = ref.recursive or recursive
    ref.governance_wide = ref.governance_wide or governance_wide


def _roadmap_capabilities(item: dict[str, Any]) -> set[str]:
    links = item.get("capability_links", [])
    result: set[str] = set()
    if isinstance(links, list):
        for link in links:
            if isinstance(link, dict) and link.get("id"):
                result.add(str(link["id"]))
    # Read legacy input snapshots defensively so removals from an older PR base remain detectable.
    legacy = item.get("capabilities", [])
    if isinstance(legacy, list):
        result.update(str(value) for value in legacy if value)
    return result


def build_snapshot(
    registry: dict[str, Any],
    mapping: dict[str, Any],
    roadmap: dict[str, Any] | None,
    *,
    root: Path | None = ROOT,
    input_hashes: dict[str, str] | None = None,
) -> Snapshot:
    capabilities = registry.get("capabilities")
    if not isinstance(capabilities, list):
        raise ValueError("registry is missing capabilities[]")
    known = {str(capability["id"]) for capability in capabilities}
    references: dict[str, Reference] = {}
    dependents: dict[str, set[str]] = defaultdict(set)

    for capability in capabilities:
        capability_id = str(capability["id"])
        for key in ("services", "ui_consumers", "mobile_consumers", "tests"):
            values = capability.get(key, [])
            if not isinstance(values, list):
                continue
            for value in values:
                add_reference(
                    references,
                    value,
                    [capability_id],
                    source=f"registry:{key}",
                )
        for value in capability.get("apis", []) or []:
            path = extract_repository_path(value)
            if path:
                add_reference(
                    references,
                    path,
                    [capability_id],
                    source="registry:apis",
                )
        for evidence in capability.get("evidence", []) or []:
            if not isinstance(evidence, dict) or evidence.get("type") != "repository":
                continue
            add_reference(
                references,
                evidence.get("path"),
                [capability_id],
                source="registry:evidence",
            )
        for dependency in capability.get("dependencies", []) or []:
            dependency_id = str(dependency)
            if dependency_id in known:
                dependents[dependency_id].add(capability_id)

    mapping_rows = mapping.get("capabilities", [])
    if not isinstance(mapping_rows, list):
        raise ValueError("mapping is missing capabilities[]")
    for row in mapping_rows:
        capability_id = str(row.get("capability_id") or "")
        if capability_id not in known:
            continue
        for dimension in MAPPING_DIMENSIONS:
            values = row.get(dimension, [])
            if not isinstance(values, list):
                continue
            for value in values:
                path = extract_repository_path(value)
                if path:
                    add_reference(
                        references,
                        path,
                        [capability_id],
                        source=f"mapping:{dimension}",
                    )

    if isinstance(roadmap, dict):
        items = roadmap.get("items", [])
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                item_id = str(item.get("id") or "unknown")
                linked = _roadmap_capabilities(item) & known
                impact_scope = str(item.get("impact_scope") or "linked_capabilities")
                scope_capabilities = known if impact_scope == "all_capabilities" else linked
                governance_wide = impact_scope == "all_capabilities"
                source_path = item.get("source")
                if source_path and scope_capabilities:
                    add_reference(
                        references,
                        source_path,
                        scope_capabilities,
                        source=f"roadmap:{item_id}:source",
                        governance_wide=governance_wide,
                    )
                for scope in item.get("governance_scope", []) or []:
                    recursive = False
                    if root is not None:
                        try:
                            recursive = (root / normalize_repo_path(scope)).is_dir()
                        except ValueError:
                            recursive = False
                    # Directory scopes in historical snapshots may not exist in the head tree.
                    if str(scope).endswith("/") or PurePosixPath(str(scope)).suffix == "":
                        recursive = recursive or True
                    add_reference(
                        references,
                        scope,
                        scope_capabilities,
                        source=f"roadmap:{item_id}:governance",
                        recursive=recursive,
                        governance_wide=governance_wide,
                    )
            # Editing the linkage source can add or remove any capability. Require an explicit
            # governance-wide declaration rather than trusting only the post-change links.
            add_reference(
                references,
                ROADMAP_PATH.as_posix(),
                known,
                source="roadmap:definition",
                governance_wide=True,
            )

    for governance_path in (
        ROADMAP_LINKER_PATH,
        GATE_PATH,
        LEGACY_IMPACT_PATH,
        WORKFLOW_PATH,
    ):
        add_reference(
            references,
            governance_path.as_posix(),
            known,
            source="capability-governance-core",
            governance_wide=True,
        )

    return Snapshot(
        references=references,
        dependents={key: set(value) for key, value in dependents.items()},
        known_capabilities=known,
        input_hashes=dict(input_hashes or {}),
    )


def merge_snapshots(*snapshots: Snapshot) -> Snapshot:
    references: dict[str, Reference] = {}
    dependents: dict[str, set[str]] = defaultdict(set)
    known: set[str] = set()
    input_hashes: dict[str, str] = {}
    for snapshot in snapshots:
        known.update(snapshot.known_capabilities)
        input_hashes.update(snapshot.input_hashes)
        for dependency, values in snapshot.dependents.items():
            dependents[dependency].update(values)
        for path, incoming in snapshot.references.items():
            current = references.setdefault(path, Reference())
            current.capabilities.update(incoming.capabilities)
            current.sources.update(incoming.sources)
            current.recursive = current.recursive or incoming.recursive
            current.governance_wide = current.governance_wide or incoming.governance_wide
    return Snapshot(
        references=references,
        dependents={key: set(value) for key, value in dependents.items()},
        known_capabilities=known,
        input_hashes=input_hashes,
    )


def _load_current_json(relative_path: Path, *, root: Path = ROOT) -> tuple[dict[str, Any], str]:
    content = (root / relative_path).read_bytes()
    return json.loads(content), sha256_bytes(content)


def _load_current_yaml(relative_path: Path, *, root: Path = ROOT) -> tuple[dict[str, Any], str]:
    content = (root / relative_path).read_bytes()
    data = yaml.safe_load(content.decode("utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{relative_path}: expected a YAML mapping")
    return data, sha256_bytes(content)


def current_snapshot(*, root: Path = ROOT) -> Snapshot:
    registry, registry_hash = _load_current_json(REGISTRY_PATH, root=root)
    mapping, mapping_hash = _load_current_json(MAPPING_PATH, root=root)
    roadmap, roadmap_hash = _load_current_yaml(ROADMAP_PATH, root=root)
    return build_snapshot(
        registry,
        mapping,
        roadmap,
        root=root,
        input_hashes={
            REGISTRY_PATH.as_posix(): registry_hash,
            MAPPING_PATH.as_posix(): mapping_hash,
            ROADMAP_PATH.as_posix(): roadmap_hash,
        },
    )


def git(*args: str, root: Path = ROOT, check: bool = True) -> subprocess.CompletedProcess[bytes]:
    return subprocess.run(
        ["git", *args],
        cwd=root,
        capture_output=True,
        check=check,
    )


def git_text_at(ref: str, relative_path: Path, *, root: Path = ROOT) -> bytes | None:
    result = git("show", f"{ref}:{relative_path.as_posix()}", root=root, check=False)
    if result.returncode != 0:
        return None
    return result.stdout


def snapshot_at_ref(ref: str, *, root: Path = ROOT) -> Snapshot | None:
    registry_bytes = git_text_at(ref, REGISTRY_PATH, root=root)
    mapping_bytes = git_text_at(ref, MAPPING_PATH, root=root)
    if registry_bytes is None or mapping_bytes is None:
        return None
    roadmap_bytes = git_text_at(ref, ROADMAP_PATH, root=root)
    registry = json.loads(registry_bytes)
    mapping = json.loads(mapping_bytes)
    roadmap: dict[str, Any] | None = None
    input_hashes = {
        f"{ref}:{REGISTRY_PATH.as_posix()}": sha256_bytes(registry_bytes),
        f"{ref}:{MAPPING_PATH.as_posix()}": sha256_bytes(mapping_bytes),
    }
    if roadmap_bytes is not None:
        loaded = yaml.safe_load(roadmap_bytes.decode("utf-8"))
        if isinstance(loaded, dict):
            roadmap = loaded
            input_hashes[f"{ref}:{ROADMAP_PATH.as_posix()}"] = sha256_bytes(roadmap_bytes)
    return build_snapshot(
        registry,
        mapping,
        roadmap,
        root=None,
        input_hashes=input_hashes,
    )


def merge_base(base: str, head: str, *, root: Path = ROOT) -> str:
    result = git("merge-base", base, head, root=root)
    value = result.stdout.decode("utf-8").strip()
    if not value:
        raise ValueError("git merge-base returned an empty result")
    return value


def parse_name_status_z(payload: bytes) -> list[str]:
    fields = payload.decode("utf-8", errors="surrogateescape").split("\0")
    if fields and fields[-1] == "":
        fields.pop()
    changed: list[str] = []
    index = 0
    while index < len(fields):
        status = fields[index]
        index += 1
        if not status:
            continue
        code = status[0]
        path_count = 2 if code in {"R", "C"} else 1
        if index + path_count > len(fields):
            raise ValueError(f"malformed git --name-status output near {status!r}")
        for _ in range(path_count):
            changed.append(normalize_repo_path(fields[index]))
            index += 1
    return sorted(set(changed))


def git_changed_paths(base: str, head: str, *, root: Path = ROOT) -> tuple[str, list[str]]:
    base_commit = merge_base(base, head, root=root)
    result = git(
        "diff",
        "--name-status",
        "-z",
        "--find-renames=50%",
        f"{base_commit}..{head}",
        root=root,
    )
    return base_commit, parse_name_status_z(result.stdout)


def worktree_deviation(head: str, *, root: Path = ROOT) -> list[str]:
    """المسارات التي تختلف بين الشجرة/الفهرس و``head`` — أي ما **لن تراه** المقارنة.

    ``git_changed_paths`` يقارن ``base..head`` بمراجعَ **ملتزَمة** حصراً. فاشتقاقُ
    الأثر بينما في الشجرة تعديلٌ غير ملتزَم يُنتج جواباً عن شجرةٍ أخرى — وهو ما وقع
    في #859: اشتُقّ السطر بعد ``git add`` وقبل الالتزام، فلم تدخل المصنوعات المُعاد
    توليدها في الفرق وسقطت قدرتان، فحجبت CI.

    ``[]`` حين لا يكون ``head`` هو نسخة العمل (SHA صريح مثلاً): عندئذٍ لا معنى
    لمقارنة الشجرة أصلاً، والسؤال المطروح تاريخيّ لا حاليّ.
    """
    try:
        resolved = git("rev-parse", head, root=root).stdout.decode("utf-8", "replace").strip()
        current_head = git("rev-parse", "HEAD", root=root).stdout.decode("utf-8", "replace").strip()
    except Exception:  # noqa: BLE001 — تعذّر الحلّ ⇒ لا ندّعي انحرافاً
        return []
    if resolved != current_head:
        return []
    # `--porcelain=v1 -z` لا `--porcelain` وحده: التقسيم بالأسطر و`strip()` يكسر على
    # أسماء فيها مسافة بادئة/لاحقة أو سطرٌ جديد (وgit يقتبسها عندئذٍ فيتشوّه المسار).
    # وهي سابقة البيت في `scripts/ci/test_impact.py` و`scripts/ops/pre_push_stability_guard.py`.
    status = git("status", "--porcelain=v1", "-z", "--untracked-files=all", root=root, check=False)
    fields = [f for f in status.stdout.decode("utf-8", "replace").split("\0") if f]
    paths: list[str] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        code, path = entry[:2], entry[3:]
        paths.append(path)
        if "R" in code or "C" in code:
            index += 1  # إعادة التسمية تحمل مصدرها في الحقل التالي
        index += 1
    return sorted(set(paths))


def impact(paths: Iterable[str], snapshot: Snapshot | None = None) -> dict[str, Any]:
    active = snapshot or current_snapshot()
    normalized_paths = sorted({normalize_repo_path(path) for path in paths if str(path).strip()})
    direct: set[str] = set()
    matched_paths: dict[str, set[str]] = defaultdict(set)
    matched_sources: dict[str, set[str]] = defaultdict(set)
    governance_wide = False

    for changed in normalized_paths:
        for reference_path, reference in active.references.items():
            matched = changed == reference_path
            if not matched and reference.recursive:
                matched = changed.startswith(reference_path.rstrip("/") + "/")
            if not matched:
                continue
            direct.update(reference.capabilities)
            governance_wide = governance_wide or reference.governance_wide
            for capability_id in reference.capabilities:
                matched_paths[capability_id].add(changed)
                matched_sources[capability_id].update(reference.sources)

    affected = set(direct)
    queue = deque(sorted(direct))
    while queue:
        capability_id = queue.popleft()
        for dependent in sorted(active.dependents.get(capability_id, set())):
            if dependent not in affected:
                affected.add(dependent)
                queue.append(dependent)

    return {
        "schema_version": SCHEMA_VERSION,
        "changed_paths": normalized_paths,
        "direct": sorted(direct),
        "transitive": sorted(affected - direct),
        "affected": sorted(affected),
        "matched_paths": {key: sorted(value) for key, value in sorted(matched_paths.items())},
        "matched_sources": {key: sorted(value) for key, value in sorted(matched_sources.items())},
        "governance_wide": governance_wide,
        "runtime_claims": False,
        "production_certification": False,
    }


def parse_declaration_value(value: str, known: set[str]) -> dict[str, Any]:
    raw = value.strip()
    if not raw:
        return {"mode": "missing", "declared": [], "unknown": [], "errors": []}
    tokens = [token.strip().upper() for token in raw.split(",") if token.strip()]
    errors: list[str] = []
    if not tokens:
        return {"mode": "missing", "declared": [], "unknown": [], "errors": []}
    if "ALL" in tokens:
        if tokens != ["ALL"]:
            errors.append("ALL must be the only Capability-Impact token")
        return {"mode": "all", "declared": sorted(known), "unknown": [], "errors": errors}
    if "NONE" in tokens:
        if tokens != ["NONE"]:
            errors.append("NONE must be the only Capability-Impact token")
        return {"mode": "none", "declared": [], "unknown": [], "errors": errors}
    duplicates = sorted({token for token in tokens if tokens.count(token) > 1})
    if duplicates:
        errors.append("duplicate capability ids: " + ",".join(duplicates))
    malformed = sorted({token for token in tokens if not CAPABILITY_ID_RE.fullmatch(token)})
    if malformed:
        errors.append("malformed capability ids: " + ",".join(malformed))
    declared = set(tokens)
    unknown = sorted(declared - known)
    return {
        "mode": "explicit",
        "declared": sorted(declared),
        "unknown": unknown,
        "errors": errors,
    }


def parse_pr_body(body: str, known: set[str]) -> dict[str, Any]:
    matches = DECLARATION_RE.findall(body or "")
    if len(matches) > 1:
        return {
            "mode": "invalid",
            "declared": [],
            "unknown": [],
            "errors": ["multiple Capability-Impact lines are not allowed"],
        }
    return parse_declaration_value(matches[0] if matches else "", known)


def read_pr_body(path: str | Path) -> tuple[str, str]:
    """Read the exact declaration subject and return its auditable digest."""
    raw = Path(path).read_bytes()
    return raw.decode("utf-8"), sha256_bytes(raw)


def apply_declaration(
    data: dict[str, Any], declaration: dict[str, Any], known: set[str]
) -> dict[str, Any]:
    direct = set(data["direct"])
    affected = set(data["affected"])
    declared = set(declaration.get("declared", []))
    mode = declaration.get("mode", "missing")
    errors = list(declaration.get("errors", []))
    unknown = sorted(set(declaration.get("unknown", [])))

    missing_direct = sorted(direct - declared)
    unaffected_declared = sorted((declared & known) - affected)

    if mode == "all":
        missing_direct = []
        unaffected_declared = [] if data.get("governance_wide") else sorted(known - affected)
        if not data.get("governance_wide"):
            errors.append("ALL is allowed only for governance-wide changes")
    elif mode == "none":
        missing_direct = sorted(direct)
        if direct:
            errors.append("NONE is invalid because direct capability impact exists")
    elif mode == "missing" and direct:
        missing_direct = sorted(direct)
    elif mode == "invalid":
        missing_direct = sorted(direct)

    block = bool(errors or unknown or missing_direct or unaffected_declared)
    data["declaration"] = {
        "mode": mode,
        "declared": sorted(declared),
        "missing_direct": missing_direct,
        "unknown_capabilities": unknown,
        "unaffected_declared": unaffected_declared,
        "errors": errors,
        "required": bool(direct),
    }
    data["decision"] = "BLOCK" if block else "PASS"
    return data


def index_summary(snapshot: Snapshot | None = None, *, root: Path = ROOT) -> dict[str, Any]:
    active = snapshot or current_snapshot(root=root)
    recursive = sum(reference.recursive for reference in active.references.values())
    governance_wide = sum(reference.governance_wide for reference in active.references.values())
    inputs = dict(sorted(active.input_hashes.items()))
    for relative_path in (GATE_PATH, ROADMAP_LINKER_PATH, LEGACY_IMPACT_PATH, WORKFLOW_PATH):
        target = root / relative_path
        if target.is_file():
            inputs[relative_path.as_posix()] = sha256_bytes(target.read_bytes())
    return {
        "schema_version": SCHEMA_VERSION,
        "indexed_paths": len(active.references),
        "recursive_scopes": recursive,
        "governance_wide_paths": governance_wide,
        "capabilities": len(active.known_capabilities),
        "inputs": dict(sorted(inputs.items())),
        "constraints": {
            "merge_base_snapshot_union": True,
            "rename_old_and_new_paths": True,
            "deletion_detection": True,
            "runtime_claims": False,
            "production_certification": False,
        },
    }


def render_index_summary(summary: dict[str, Any]) -> bytes:
    return (json.dumps(summary, indent=2, ensure_ascii=False) + "\n").encode("utf-8")


def write_output(path: str | None, payload: bytes) -> None:
    if path:
        target = Path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(payload)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("paths", nargs="*")
    parser.add_argument("--paths-file")
    parser.add_argument("--base")
    parser.add_argument("--head", "--head-ref", dest="head")
    parser.add_argument("--declared")
    parser.add_argument("--pr-body-file")
    parser.add_argument("--pr-number", type=int)
    parser.add_argument("--output")
    parser.add_argument(
        "--allow-dirty-tree",
        action="store_true",
        help=(
            "اشتقّ رغم وجود تعديلات غير ملتزَمة. الناتج عندئذٍ **لا يطابق** ما تحسبه "
            "CI، فلا يُبنى عليه إعلان."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--generate-index", action="store_true")
    mode.add_argument("--check-index", action="store_true")
    args = parser.parse_args(argv)

    try:
        current = current_snapshot()
        if args.generate_index or args.check_index:
            summary = index_summary(current)
            content = render_index_summary(summary)
            if args.generate_index:
                OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
                INDEX_SUMMARY_PATH.write_bytes(content)
            else:
                if not INDEX_SUMMARY_PATH.is_file() or INDEX_SUMMARY_PATH.read_bytes() != content:
                    print("capability impact index drift; run --generate-index", file=sys.stderr)
                    return 1
            print(
                "capability_impact_index_ok "
                f"paths={summary['indexed_paths']} capabilities={summary['capabilities']}"
            )
            return 0

        if bool(args.base) != bool(args.head):
            raise ValueError("--base and --head must be provided together")
        if args.declared is not None and args.pr_body_file:
            raise ValueError("use either --declared or --pr-body-file, not both")
        if args.pr_number is not None and not args.pr_body_file:
            raise ValueError("--pr-number requires --pr-body-file")

        paths = list(args.paths)
        if args.paths_file:
            paths.extend(Path(args.paths_file).read_text(encoding="utf-8").splitlines())

        base_commit: str | None = None
        active_snapshot = current
        if args.base and args.head:
            # fail-closed على الاشتقاق من شجرةٍ غير ملتزَمة: الجواب حينها عن شجرةٍ
            # أخرى غير التي ستقيسها CI، والإعلان المبنيّ عليه يبيت قبل أن يُكتَب.
            if not args.allow_dirty_tree:
                deviation = worktree_deviation(args.head)
                if deviation:
                    print(
                        "الاشتقاق مرفوض: الشجرة تحمل تعديلات غير ملتزَمة بينما "
                        f"--head={args.head} هو نسخة العمل. المقارنة `base..head` تقرأ "
                        "**المُلتزَم** لا الفهرس، فالناتج لا يطابق ما تحسبه CI.\n"
                        "  التزِم أوّلاً ثمّ أعِد الاشتقاق (أو --allow-dirty-tree "
                        "للاستكشاف بلا بناء إعلانٍ عليه).\n"
                        "  المنحرف: " + ", ".join(sorted(deviation)[:10]),
                        file=sys.stderr,
                    )
                    return 2
            base_commit, git_paths = git_changed_paths(args.base, args.head)
            paths.extend(git_paths)
            historical = snapshot_at_ref(base_commit)
            if historical is not None:
                active_snapshot = merge_snapshots(historical, current)

        data = impact(paths, active_snapshot)
        data["git"] = {
            "base": args.base,
            "head": args.head,
            "merge_base": base_commit,
        }

        declaration_subject: dict[str, Any] | None = None
        if args.pr_body_file:
            pr_body, pr_body_sha256 = read_pr_body(args.pr_body_file)
            declaration = parse_pr_body(pr_body, active_snapshot.known_capabilities)
            declaration_subject = {
                "kind": "live_pr_body",
                "pr_number": args.pr_number,
                "sha256": pr_body_sha256,
            }
        elif args.declared is not None:
            declaration = parse_declaration_value(args.declared, active_snapshot.known_capabilities)
        else:
            declaration = parse_declaration_value("", active_snapshot.known_capabilities)
        apply_declaration(data, declaration, active_snapshot.known_capabilities)
        if declaration_subject is not None:
            data["declaration"]["subject"] = declaration_subject

        content = (json.dumps(data, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
        write_output(args.output, content)
        sys.stdout.buffer.write(content)
        return 1 if data["decision"] == "BLOCK" else 0
    except (
        OSError,
        ValueError,
        json.JSONDecodeError,
        yaml.YAMLError,
        subprocess.CalledProcessError,
    ) as exc:
        print(str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
