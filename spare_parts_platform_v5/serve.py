from __future__ import annotations

import os

from waitress import serve

from app import app


def main() -> None:
    if app.config["SECRET_KEY"] == "dev-change-this-key":
        raise RuntimeError("Set a strong SECRET_KEY before starting the production server.")

    serve(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "5055")),
        threads=int(os.environ.get("WAITRESS_THREADS", "8")),
        channel_timeout=int(os.environ.get("WAITRESS_CHANNEL_TIMEOUT", "120")),
        trusted_proxy=os.environ.get("TRUSTED_PROXY", "127.0.0.1"),
        trusted_proxy_count=1,
        trusted_proxy_headers={
            "x-forwarded-for",
            "x-forwarded-host",
            "x-forwarded-proto",
            "x-forwarded-port",
        },
        clear_untrusted_proxy_headers=True,
        expose_tracebacks=False,
        ident="SparePartsPlatform",
    )


if __name__ == "__main__":
    main()
