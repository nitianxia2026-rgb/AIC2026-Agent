#!/usr/bin/env python3
"""本地验证 bid_api：10次连续成功、业务拒绝、鉴权和OpenAPI契约。"""

from __future__ import annotations

import json
import threading
import urllib.error
import urllib.request

from bid_api import API_VERSION, create_server
from bid_simulator import DEFAULT_INPUT, PARAM_VERSION

API_KEY = "local-verification-key"


def request_json(url: str, method: str = "GET", payload: dict | None = None, key: str = ""):
    data = None if payload is None else json.dumps(payload, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if key:
        headers["X-API-Key"] = key
    request = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=3) as response:
            return response.status, json.loads(response.read())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read())


def main() -> None:
    server = create_server("127.0.0.1", 0, DEFAULT_INPUT, API_KEY)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = f"http://127.0.0.1:{server.server_address[1]}"
    checks: list[tuple[str, bool]] = []
    try:
        status, health = request_json(base + "/healthz")
        checks.append(("健康检查", status == 200 and health.get("parameter_version") == PARAM_VERSION))

        status, schema = request_json(base + "/openapi.json")
        checks.append((
            "OpenAPI契约",
            status == 200
            and schema.get("openapi") == "3.0.3"
            and schema.get("info", {}).get("version") == API_VERSION
            and schema.get("paths", {}).get("/bid-simulate", {}).get("post", {}).get("operationId") == "bid_simulate"
            and set(schema.get("paths", {})) == {"/bid-simulate"},
        ))

        valid = {
            "industry": "餐饮美食", "ad_type": "信息流广告", "billing_type": "CPM",
            "objective": "留资", "daily_budget": 500, "current_bid": 20,
            "spend_ratio": 0.6, "tracking_ready": True, "audit_status": "通过",
        }
        ten_results = []
        for _ in range(10):
            status, result = request_json(base + "/bid-simulate", "POST", valid, API_KEY)
            ten_results.append((status, result))
        checks.append((
            "连续10次成功",
            all(
                status == 200
                and result.get("status") == "ok"
                and result.get("parameter_version") == PARAM_VERSION
                and result.get("recommendation", {}).get("first_test_bid") == 20.0
                and result.get("recommendation", {}).get("test_band_low_bid") == 18.0
                and result.get("recommendation", {}).get("test_band_high_bid") == 22.0
                and len(result.get("three_cases", [])) == 3
                for status, result in ten_results
            ),
        ))
        checks.append((
            "十次结果确定性一致",
            len({json.dumps(result, ensure_ascii=False, sort_keys=True) for _, result in ten_results}) == 1,
        ))

        invalid_billing = dict(valid, billing_type="CPC")
        status, result = request_json(base + "/bid-simulate", "POST", invalid_billing, API_KEY)
        checks.append((
            "计费冲突业务拒绝",
            status == 200 and result.get("status") == "refused"
            and result.get("reason_code") == "BILLING_TYPE_MISMATCH",
        ))

        missing_ratio = dict(valid)
        missing_ratio.pop("spend_ratio")
        status, result = request_json(base + "/bid-simulate", "POST", missing_ratio, API_KEY)
        checks.append((
            "消耗比例缺失业务拒绝",
            status == 200 and result.get("status") == "refused"
            and result.get("reason_code") == "MISSING_SPEND_RATIO",
        ))

        missing_tracking = dict(valid)
        missing_tracking.pop("tracking_ready")
        status, result = request_json(base + "/bid-simulate", "POST", missing_tracking, API_KEY)
        checks.append((
            "留资回传状态缺失业务拒绝",
            status == 200 and result.get("status") == "refused"
            and result.get("reason_code") == "MISSING_TRACKING_READY",
        ))

        tracking_not_ready = dict(valid, tracking_ready=False)
        status, result = request_json(base + "/bid-simulate", "POST", tracking_not_ready, API_KEY)
        checks.append((
            "回传未就绪业务拒绝",
            status == 200 and result.get("status") == "refused"
            and result.get("reason_code") == "TRACKING_NOT_READY",
        ))

        status, result = request_json(base + "/bid-simulate", "POST", valid)
        checks.append(("鉴权拒绝", status == 401 and result.get("reason_code") == "UNAUTHORIZED"))

        malformed = urllib.request.Request(
            base + "/bid-simulate", data=b"[]", method="POST",
            headers={"Content-Type": "application/json", "X-API-Key": API_KEY},
        )
        try:
            urllib.request.urlopen(malformed, timeout=3)
            malformed_result = (0, {})
        except urllib.error.HTTPError as error:
            malformed_result = (error.code, json.loads(error.read()))
        checks.append((
            "非法JSON结构拒绝",
            malformed_result[0] == 400 and malformed_result[1].get("reason_code") == "INVALID_JSON_OBJECT",
        ))
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)

    for name, passed in checks:
        print(f"{'PASS' if passed else 'FAIL'} {name}", flush=True)
    passed_count = sum(passed for _, passed in checks)
    print(
        f"checks={len(checks)} passed={passed_count} api={API_VERSION} algorithm={PARAM_VERSION}",
        flush=True,
    )
    if passed_count != len(checks):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
