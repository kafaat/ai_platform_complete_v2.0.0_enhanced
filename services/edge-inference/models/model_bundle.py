"""Bind a verified weight snapshot to the session and its inference contract."""

from __future__ import annotations

import hashlib
import json
import logging
import os
import stat
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from model_artifact_gate import expected_sha256, normalize_sha256
from models import onnx_providers
from models.errors import ModelOutputContractError
from models.pest_detector import (
    DEFAULT_PEST_LABELS_PATH,
    PEST_INPUT_SIZE,
    PEST_LABELS_ENV,
    YOLO_BOX_ROWS,
    EdgePestDetector,
    parse_label_manifest,
)
from models.yield_estimator import YIELD_INPUT_SIZE

logger = logging.getLogger(__name__)
_DEFAULT_LABELS_SHA256 = "70a7a179ee3294cc8e6b0122b9cc81f125d6178baf39332578796ea559643b21"


@dataclass(frozen=True)
class Preprocessing:
    profile: str
    input_size: tuple[int, int]
    model_shape: tuple[int, ...]


# A new preprocessing implementation needs a new profile. Sizes and input layout
# are taken from the same contract during activation and inference.
_PEST = Preprocessing("rgb640-chw-f32-v1", PEST_INPUT_SIZE, (1, 3, *PEST_INPUT_SIZE))
_YIELD = Preprocessing("rgb224-yield-features-v1", YIELD_INPUT_SIZE, (1, 6))


@dataclass(frozen=True)
class ModelBundle:
    session: Any
    input_name: str
    weight_path: str
    weight_sha256: str
    labels: tuple[tuple[str, str], ...]
    labels_sha256: str | None
    preprocessing: Preprocessing
    sha256: str


@dataclass(frozen=True)
class _Approval:
    weights: Path
    weights_sha256: str | None
    labels: Path | None
    labels_sha256: str | None


class _Unavailable(Exception):
    pass


def open_session(weights: bytes, device: str):
    """Initialize ORT from the exact approved bytes, without reopening the path."""
    import onnxruntime as ort

    providers = onnx_providers(device)
    available = set(ort.get_available_providers())
    selected = [provider for provider in providers if provider in available]
    if not selected:
        raise RuntimeError("configured_onnx_provider_unavailable")
    session = ort.InferenceSession(weights, providers=selected)
    if not set(session.get_providers()).intersection(selected):
        raise RuntimeError("configured_onnx_provider_not_loaded")
    return session


def _local_file(manifest: Path, name: object) -> Path:
    if (
        not isinstance(name, str)
        or not name
        or "\0" in name
        or Path(name).name != name
        or name in {".", ".."}
    ):
        raise _Unavailable("model_bundle_manifest_invalid")
    return manifest.with_name(name)


def _approval(path: str, sha_env: str, profile: Preprocessing) -> _Approval:
    manifest_path = os.getenv(sha_env.removesuffix("_SHA256") + "_BUNDLE_MANIFEST", "").strip()
    if manifest_path:
        manifest = Path(manifest_path)
        try:
            entry = json.loads(manifest.read_bytes())
        except (OSError, ValueError) as exc:
            raise _Unavailable("model_bundle_manifest_invalid") from exc
        if not isinstance(entry, dict):
            raise _Unavailable("model_bundle_manifest_invalid")
        if entry.get("preprocessing") != profile.profile:
            raise _Unavailable("model_preprocessing_unsupported")
        return _Approval(
            _local_file(manifest, entry.get("weights")),
            normalize_sha256(entry.get("weights_sha256")),
            _local_file(manifest, entry.get("labels")) if profile is _PEST else None,
            normalize_sha256(entry.get("labels_sha256")) if profile is _PEST else None,
        )

    labels = None
    labels_sha = None
    if profile is _PEST:
        label_path = os.getenv(PEST_LABELS_ENV, "").strip()
        labels = Path(label_path) if label_path else DEFAULT_PEST_LABELS_PATH
        labels_sha = expected_sha256("PEST_LABELS_SHA256") if label_path else _DEFAULT_LABELS_SHA256
    return _Approval(Path(path), expected_sha256(sha_env), labels, labels_sha)


def _stat_key(path: Path) -> tuple[int, ...]:
    metadata = path.stat()
    if not stat.S_ISREG(metadata.st_mode):
        raise OSError("model bundle artifacts must be regular files")
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
        metadata.st_ctime_ns,
    )


def _validate_session(session, profile: Preprocessing, class_count: int) -> str:
    inputs = session.get_inputs()
    if len(inputs) != 1 or not inputs[0].name or inputs[0].type != "tensor(float)":
        raise _Unavailable("model_input_contract_violation")
    shape = inputs[0].shape
    if len(shape) != len(profile.model_shape) or any(
        isinstance(actual, int) and actual != expected
        for actual, expected in zip(shape, profile.model_shape, strict=True)
    ):
        raise _Unavailable("model_input_contract_violation")
    outputs = session.get_outputs()
    if not outputs or outputs[0].type not in {"tensor(float)", "tensor(double)", "tensor(float16)"}:
        raise _Unavailable("model_output_contract_violation")
    if profile is _PEST:
        shape = outputs[0].shape
        width = YOLO_BOX_ROWS + class_count
        if (
            len(shape) not in {2, 3}
            or (len(shape) == 3 and isinstance(shape[0], int) and shape[0] != 1)
            or not any(
                isinstance(dimension, int) and dimension == width for dimension in shape[-2:]
            )
        ):
            raise _Unavailable("pest_model_label_contract_violation")
    elif len(outputs[0].shape) > 2 or any(
        not isinstance(dimension, int) or dimension != 1 for dimension in outputs[0].shape
    ):
        raise _Unavailable("model_output_contract_violation")
    return inputs[0].name


class ModelBundleStore:
    """Keep one current bundle per model and publish only complete activations."""

    def __init__(self) -> None:
        self._lock = Lock()
        self._active: dict[Preprocessing, tuple[tuple, ModelBundle]] = {}

    def health_snapshot(self) -> dict[str, bool]:
        """Read the published bundle pointers without acquiring the activation lock."""
        return {
            "pest_detector": _PEST in self._active,
            "yield_estimator": _YIELD in self._active,
        }

    def resolve(
        self, *, path: str, sha_env: str, runtime_available: bool, device: str
    ) -> tuple[dict[str, object], ModelBundle | None]:
        profile = _PEST if sha_env == "PEST_MODEL_SHA256" else _YIELD
        capability = {
            "active": False,
            "model_path": path,
            "model_file_present": False,
            "onnxruntime_available": runtime_available,
            "sha256_env": sha_env,
            "expected_sha256": None,
            "actual_sha256": None,
            "sha256_verified": False,
            "reason": None,
        }
        bundle = None
        try:
            with self._lock:
                approval = _approval(path, sha_env, profile)
                capability["model_path"] = str(approval.weights)
                capability["expected_sha256"] = approval.weights_sha256
                bundle = self._activate(approval, profile, device, runtime_available, capability)
        except _Unavailable as exc:
            capability["reason"] = str(exc)
        if bundle is not None:
            capability.update(
                active=True,
                bundle_sha256=bundle.sha256,
                labels_sha256=bundle.labels_sha256,
                preprocessing=bundle.preprocessing.profile,
            )
        return capability, bundle

    def _activate(
        self,
        approval: _Approval,
        profile: Preprocessing,
        device: str,
        runtime_available: bool,
        capability: dict[str, object],
    ) -> ModelBundle:
        try:
            weight_key = _stat_key(approval.weights)
        except FileNotFoundError as exc:
            raise _Unavailable("model_file_missing") from exc
        except (OSError, ValueError) as exc:
            raise _Unavailable("model_file_unreadable") from exc
        capability["model_file_present"] = True
        if approval.weights_sha256 is None:
            raise _Unavailable("model_sha256_missing_or_invalid")
        try:
            label_key = _stat_key(approval.labels) if approval.labels is not None else None
        except (OSError, ValueError) as exc:
            raise _Unavailable("pest_model_label_contract_violation") from exc
        key = approval, weight_key, label_key, device
        current = self._active.get(profile)
        if runtime_available and current is not None and current[0] == key:
            bundle = current[1]
            capability.update(actual_sha256=bundle.weight_sha256, sha256_verified=True)
            return bundle

        try:
            weights = approval.weights.read_bytes()
        except (OSError, ValueError) as exc:
            raise _Unavailable("model_file_unreadable") from exc
        actual = hashlib.sha256(weights).hexdigest()
        capability["actual_sha256"] = actual
        if actual != approval.weights_sha256:
            raise _Unavailable("model_sha256_mismatch")
        capability["sha256_verified"] = True
        if not runtime_available:
            raise _Unavailable("onnxruntime_missing")
        labels = self._labels(approval)
        try:
            session = open_session(weights, device)
            input_name = _validate_session(session, profile, len(labels))
        except _Unavailable:
            raise
        except Exception as exc:
            logger.warning("Could not initialize ONNX bundle for %s: %s", profile.profile, exc)
            raise _Unavailable("model_session_unavailable") from exc

        identity = json.dumps(
            [
                "sahool.model-bundle/v1",
                actual,
                approval.labels_sha256,
                profile.profile,
                profile.input_size,
                profile.model_shape,
            ],
            separators=(",", ":"),
        ).encode("utf-8")
        bundle = ModelBundle(
            session,
            input_name,
            str(approval.weights),
            actual,
            labels,
            approval.labels_sha256,
            profile,
            hashlib.sha256(identity).hexdigest(),
        )
        self._active[profile] = key, bundle
        return bundle

    @staticmethod
    def _labels(approval: _Approval) -> tuple[tuple[str, str], ...]:
        if approval.labels is None:
            return ()
        if approval.labels_sha256 is None:
            raise _Unavailable("pest_label_sha256_missing_or_invalid")
        try:
            payload = approval.labels.read_bytes()
            if hashlib.sha256(payload).hexdigest() != approval.labels_sha256:
                raise _Unavailable("pest_label_sha256_mismatch")
            return parse_label_manifest(payload, EdgePestDetector.PEST_DB)
        except (OSError, ValueError, ModelOutputContractError) as exc:
            raise _Unavailable("pest_model_label_contract_violation") from exc
