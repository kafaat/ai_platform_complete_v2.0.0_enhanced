"""Disabled-by-default CLI; do not import SDK/model code on the disabled path."""

import os


def main() -> None:
    if os.environ.get("SAHOOL_REALTIME_VOICE_ENABLED", "0") != "1":
        return
    from livekit.agents import cli
    from realtime_agent.worker import create_server

    cli.run_app(create_server())


if __name__ == "__main__":
    main()
