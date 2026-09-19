#!/usr/bin/env python3
"""投手智囊出价仿真 HTTP API（零第三方依赖）。

只读封装 bid-sim-v1.2，不连接广告账户、不修改计划。
正式接入平台前仍需部署到稳定 HTTPS、配置 API Key 并通过外网连续测试。
"""

from __future__ import annotations

import argparse
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from bid_simulator import DEFAULT_INPUT, PARAM_VERSION, load_benchmarks, recommendation, simulate_request

DISCLAIMER = "合成仿真，用于首轮测试，不代表平台最优出价"
API_VERSION = "bid-api-v0.3"


def openapi_schema(server_url: str = "https://YOUR_STABLE_HOST") -> dict[str, Any]:
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "投手智囊出价仿真 API",
            "version": API_VERSION,
            "description": "基于KB-02合成锚点的确定性首轮测试带；不代表平台实时竞价或最优出价。",
        },
        "servers": [{"url": server_url}],
        "paths": {
            "/bid-simulate": {
                "post": {
                    "operationId": "bid_simulate",
                    "summary": "生成当前出价的首测档和相邻测试带",
                    "description": "只接受信息流/开屏的CPM出价或搜索的CPC出价；oCPM目标成本与CPA出价不在当前口径内。",
                    "security": [{"ApiKeyAuth": []}],
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {"$ref": "#/components/schemas/BidSimulationRequest"}
                            }
                        },
                    },
                    "responses": {
                        "200": {
                            "description": "仿真建议或业务拒绝原因",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/BidSimulationResponse"}
                                }
                            },
                        },
                        "400": {"description": "请求不是合法JSON对象"},
                        "401": {"description": "API Key错误或缺失"},
                    },
                }
            },
        },
        "components": {
            "securitySchemes": {
                "ApiKeyAuth": {"type": "apiKey", "in": "header", "name": "X-API-Key"}
            },
            "schemas": {
                "BidSimulationRequest": {
                    "type": "object",
                    "required": [
                        "industry", "ad_type", "billing_type", "objective",
                        "daily_budget", "current_bid", "spend_ratio",
                    ],
                    "properties": {
                        "industry": {
                            "type": "string",
                            "description": "支持标准行业名，也兼容餐饮、餐饮业、教育、教培、电商、本地生活、家装等常见简称。",
                        },
                        "ad_type": {
                            "type": "string", "description": "信息流广告、开屏广告、搜索广告；兼容信息流、开屏、搜索简称。"
                        },
                        "billing_type": {"type": "string", "enum": ["CPM", "CPC"]},
                        "objective": {"type": "string", "description": "曝光、点击、留资、下单；获客或收集联系方式按留资处理。"},
                        "daily_budget": {"type": "number", "exclusiveMinimum": 0},
                        "current_bid": {"type": "number", "exclusiveMinimum": 0},
                        "spend_ratio": {
                            "type": "number", "minimum": 0, "maximum": 1,
                            "description": "当前统计周期内的预算消耗比例，例如60%传0.6；未知时不要调用。",
                        },
                        "tracking_ready": {
                            "type": "boolean",
                            "description": "留资/下单目标必填；是否已完成有效转化回传。",
                        },
                        "audit_status": {
                            "type": "string", "enum": ["通过", "未通过"],
                            "description": "可选；已知审核未通过时传“未通过”，工具将拒绝给出测试带。",
                        },
                        "material": {"type": "string", "description": "可选；不填则使用对应广告形式的默认素材口径。"},
                    },
                },
                "BidSimulationResponse": {
                    "type": "object",
                    "properties": {
                        "status": {"type": "string", "enum": ["ok", "refused"]},
                        "parameter_version": {"type": "string"},
                        "recommendation": {"type": "object", "additionalProperties": True},
                        "three_cases": {"type": "array", "items": {"type": "object", "additionalProperties": True}},
                        "reason_code": {"type": "string"},
                        "disclaimer": {"type": "string"},
                    },
                },
            },
        },
    }


def api_result(payload: dict[str, Any], benchmarks: dict) -> dict[str, Any]:
    request = dict(payload)
    request.setdefault("scenario_id", "api-request")
    rows = simulate_request(request, benchmarks)
    rec = recommendation(rows)
    if rec.get("status") != "ok":
        return {
            "status": "refused",
            "parameter_version": PARAM_VERSION,
            "reason_code": rec.get("reason_code", "NO_RESULT"),
            "disclaimer": DISCLAIMER,
        }

    selected = float(rec["first_test_multiplier"])
    three_cases = []
    for row in rows:
        if float(row["candidate_multiplier"]) != selected:
            continue
        three_cases.append({
            "case": row["case"],
            "candidate_bid": row["candidate_bid"],
            "simulated_impressions": row["simulated_impressions"],
            "simulated_clicks": row["simulated_clicks"],
            "simulated_conversions": row["simulated_conversions"],
            "simulated_spend": row["simulated_spend"],
            "simulated_cpa": row["simulated_cpa"],
            "budget_exhaustion_risk": row["budget_exhaustion_risk"],
        })

    current_bid = float(rec["current_bid"])
    return {
        "status": "ok",
        "api_version": API_VERSION,
        "parameter_version": PARAM_VERSION,
        "recommendation": {
            "current_bid": current_bid,
            "current_bid_to_anchor": rec["current_bid_to_anchor"],
            "first_test_multiplier": rec["first_test_multiplier"],
            "first_test_bid": rec["first_test_bid"],
            "test_band_low_multiplier": rec["test_band_low"],
            "test_band_low_bid": round(current_bid * float(rec["test_band_low"]), 4),
            "test_band_high_multiplier": rec["test_band_high"],
            "test_band_high_bid": round(current_bid * float(rec["test_band_high"]), 4),
            "reason_code": rec["reason_code"],
            "observe": rec["observe"],
            "stop_condition": rec["stop_condition"],
            "budget_risk": rec["budget_risk"],
        },
        "three_cases": three_cases,
        "disclaimer": DISCLAIMER,
    }


def make_handler(benchmarks: dict, api_key: str):
    class Handler(BaseHTTPRequestHandler):
        server_version = "BidSimulatorAPI/0.1"

        def _send(self, status: int, payload: dict[str, Any]) -> None:
            body = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:  # noqa: N802
            if self.path == "/healthz":
                self._send(200, {
                    "status": "ok", "api_version": API_VERSION,
                    "parameter_version": PARAM_VERSION, "disclaimer": DISCLAIMER,
                })
                return
            if self.path == "/openapi.json":
                host = self.headers.get("Host", "YOUR_STABLE_HOST")
                proto = self.headers.get("X-Forwarded-Proto", "http")
                self._send(200, openapi_schema(f"{proto}://{host}"))
                return
            self._send(404, {"status": "error", "reason_code": "NOT_FOUND"})

        def do_POST(self) -> None:  # noqa: N802
            if self.path != "/bid-simulate":
                self._send(404, {"status": "error", "reason_code": "NOT_FOUND"})
                return
            if api_key and self.headers.get("X-API-Key", "") != api_key:
                self._send(401, {"status": "error", "reason_code": "UNAUTHORIZED"})
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 65536:
                    raise ValueError("invalid body length")
                payload = json.loads(self.rfile.read(length))
                if not isinstance(payload, dict):
                    raise ValueError("body must be an object")
            except (ValueError, json.JSONDecodeError):
                self._send(400, {"status": "error", "reason_code": "INVALID_JSON_OBJECT"})
                return
            self._send(200, api_result(payload, benchmarks))

        def log_message(self, format: str, *args: object) -> None:
            return

    return Handler


def create_server(host: str, port: int, input_path: Path, api_key: str = "") -> ThreadingHTTPServer:
    benchmarks = load_benchmarks(input_path)
    server = ThreadingHTTPServer((host, port), make_handler(benchmarks, api_key))
    server.daemon_threads = True
    server.block_on_close = False
    return server


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8787")))
    parser.add_argument("--input", type=Path, default=DEFAULT_INPUT)
    args = parser.parse_args()
    api_key = os.environ.get("BID_SIM_API_KEY", "")
    if args.host not in ("127.0.0.1", "localhost", "::1") and not api_key:
        raise SystemExit("拒绝启动：非本机监听必须设置 BID_SIM_API_KEY")
    server = create_server(args.host, args.port, args.input, api_key)
    print(json.dumps({
        "status": "listening", "host": args.host, "port": args.port,
        "api_key_required": bool(api_key), "parameter_version": PARAM_VERSION,
    }, ensure_ascii=False), flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
