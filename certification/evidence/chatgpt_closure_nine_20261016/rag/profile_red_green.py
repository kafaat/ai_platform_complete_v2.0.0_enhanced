"""Same behavioral witness against actual main module and current candidate."""

import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

repo = Path(__file__).resolve().parents[4]
out = Path(__file__).parent
baseline = "6e8cc0f9952c037550ae1644919f88c475dd89a7"
results = {}
for name, raw in [
    (
        "main",
        subprocess.check_output(
            ["git", "show", baseline + ":services/sahool-platform/core/rag/production_qdrant.py"],
            cwd=repo,
        ),
    ),
    ("candidate", (repo / "services/sahool-platform/core/rag/production_qdrant.py").read_bytes()),
]:
    with tempfile.TemporaryDirectory() as directory:
        path = Path(directory) / "module.py"
        path.write_bytes(raw)
        spec = importlib.util.spec_from_file_location("profile_" + name, path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)

        class Store:
            collection = "sahool_rag_reindex_unadmitted"
            vector_size = 768

        try:
            module.HybridQdrantRetriever(Store())
            rejected = False
        except ValueError as exc:
            assert "requires an explicit serving profile" in str(exc)
            rejected = True
        results[name] = {
            "witness": "unadmitted shadow collection must refuse legacy serving",
            "passed": rejected,
        }
assert results["main"]["passed"] is False and results["candidate"]["passed"] is True
(out / "profile-red-green.json").write_text(
    json.dumps({"baseline_sha": baseline, "results": results}, indent=2) + "\n"
)
print(json.dumps(results))
