"""A familiar passage from the wrong revision or tenant cannot certify the lab upload."""

import hashlib
from pathlib import Path

import pytest

from scripts.staging import rag_fixture_probe as probe

pytestmark = pytest.mark.unit


@pytest.mark.parametrize(
    "field", ["source_revision", "document_id", "content_digest", "source_uri", "text", "chunk_id"]
)
def test_accepts_only_the_published_document(field):
    tenant = "lab-georag-test"
    raw = (Path(probe.__file__).parent / "fixtures" / probe.FILENAME).read_bytes()
    text = raw.decode().strip()
    row = {
        "source_uri": f"tenant-upload://{tenant}/{probe.FILENAME}",
        "source_revision": "sha256:" + hashlib.sha256(raw).hexdigest(),
        "document_id": hashlib.sha256(f"{tenant}:{probe.FILENAME}".encode()).hexdigest(),
        "content_digest": hashlib.sha256(text.encode()).hexdigest(),
        "text": text,
        "chunk_id": "sample-chunk",
    }
    assert probe.identify(raw, [row], tenant)["chunk_id"] == "sample-chunk"
    with pytest.raises(ValueError):
        probe.identify(raw, [{**row, field: ""}], tenant)
