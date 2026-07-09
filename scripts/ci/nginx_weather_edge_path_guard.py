#!/usr/bin/env python3
"""Static smoke guard for Nginx weather/edge exposure paths.

Runtime smoke is still required in deployment, but this catches the common drift where
/api/weather or /api/edge disappears from the production-reference nginx config.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
NGINX = ROOT / "nginx" / "nginx.v9.conf"
REQUIRED_SNIPPETS = [
    "location /api/weather/",
    "proxy_pass http://platform_backend/api/v1/weather/;",
    "location = /api/weather/readyz",
    "proxy_pass http://weather_backend/readyz;",
    "location /api/edge/",
    "proxy_pass http://platform_backend/api/edge/;",
]


def main() -> None:
    if not NGINX.exists():
        raise SystemExit("missing nginx/nginx.v9.conf")
    text = NGINX.read_text(encoding="utf-8", errors="ignore")
    missing = [snippet for snippet in REQUIRED_SNIPPETS if snippet not in text]
    if missing:
        raise SystemExit("Nginx weather/edge path guard failed; missing:\n" + "\n".join(missing))
    print("✓ nginx weather/edge path guard passed")


if __name__ == "__main__":
    main()
