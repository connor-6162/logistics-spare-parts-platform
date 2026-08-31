"""生产环境启动入口。

开发时可由 Flask 调试服务器运行；部署到 Windows 服务器后由本文件使用
Waitress 托管 WSGI 应用。监听地址、端口、线程和超时均通过环境变量配置。
"""

from __future__ import annotations

import os

from waitress import serve

from app import app


def main() -> None:
    """校验生产密钥后启动 Waitress，并信任本机反向代理转发头。"""
    # 默认开发密钥可被任何人猜到，因此生产启动时必须明确拒绝。
    if app.config["SECRET_KEY"] == "dev-change-this-key":
        raise RuntimeError("Set a strong SECRET_KEY before starting the production server.")

    # Cloudflare Tunnel 在本机转发请求，所以默认只监听 127.0.0.1，
    # 同时清理不可信代理头，防止客户端伪造真实 IP 或协议。
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
