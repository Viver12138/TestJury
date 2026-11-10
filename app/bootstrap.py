"""启动入口：先校验配置，再监听端口（ACC-M0-002）。"""

from __future__ import annotations

import os

from app.config import load_settings_or_exit


def main() -> None:
    settings = load_settings_or_exit()

    from app.main import create_app

    app = create_app(settings)

    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8000")),
        log_config=None,
        access_log=False,
    )


if __name__ == "__main__":
    main()
