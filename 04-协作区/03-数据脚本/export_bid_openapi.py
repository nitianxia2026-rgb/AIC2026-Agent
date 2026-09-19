#!/usr/bin/env python3
"""导出可直接导入API工具的OpenAPI JSON。"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from bid_api import openapi_schema

ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT = ROOT / "bid_simulate.openapi.json"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server-url", required=True, help="稳定HTTPS服务根地址，不含路径")
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()
    server_url = args.server_url.rstrip("/")
    if not server_url.startswith("https://") or "YOUR_STABLE_HOST" in server_url:
        raise SystemExit("server-url 必须是已部署的稳定HTTPS地址")
    args.output.write_text(
        json.dumps(openapi_schema(server_url), ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(f"wrote={args.output} server={server_url}")


if __name__ == "__main__":
    main()
