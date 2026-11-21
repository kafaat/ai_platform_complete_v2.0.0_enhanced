"""Separate opt-in entry point; never enables the existing voice worker."""

import os


def main():
    if os.environ.get("SAHOOL_XIAOZHI_ENABLED", "0") != "1":
        return
    import uvicorn
    from realtime_session.xiaozhi_gateway import create_gateway

    uvicorn.run(
        create_gateway(),
        host="0.0.0.0",
        port=8011,
        workers=1,
        access_log=False,
        proxy_headers=True,
        forwarded_allow_ips=os.environ.get("XIAOZHI_TRUSTED_PROXY_IPS", "127.0.0.1"),
        ws_max_size=4112,
        ws_max_queue=4,
        ws_per_message_deflate=False,
        limit_concurrency=32,
    )


if __name__ == "__main__":
    main()
