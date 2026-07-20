"""Update FILE_CHECKSUMS.sha256 using git objects (LF) to match CI Linux behavior."""
import hashlib
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CHECKSUM_FILE = ROOT / "release" / "FILE_CHECKSUMS.sha256"


def git_sha256(rel: str) -> str:
    data = subprocess.check_output(
        ["git", "show", f"HEAD:{rel}"], stderr=subprocess.DEVNULL
    )
    return hashlib.sha256(data).hexdigest()


def main() -> None:
    lines = CHECKSUM_FILE.read_text(encoding="utf-8").splitlines()
    updated = 0
    new_lines = []
    for line in lines:
        if not line.strip():
            new_lines.append(line)
            continue
        parts = line.split("  ", 1)
        if len(parts) != 2:
            new_lines.append(line)
            continue
        stored_hash, rel = parts
        try:
            correct_hash = git_sha256(rel)
        except subprocess.CalledProcessError:
            new_lines.append(line)
            continue
        if stored_hash != correct_hash:
            print(f"UPDATED: {rel}")
            new_lines.append(f"{correct_hash}  {rel}")
            updated += 1
        else:
            new_lines.append(line)
    CHECKSUM_FILE.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    print(f"Total updated: {updated}")


if __name__ == "__main__":
    main()
