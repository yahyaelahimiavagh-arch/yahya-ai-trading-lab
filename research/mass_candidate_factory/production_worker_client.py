"""Portable HTTP client for the YATL distributed coordinator control plane.

No exchange credentials, P10 state, Fresh OOS, or strategy execution lives here.
Node tokens are accepted only from the environment and are never persisted.
"""
from __future__ import annotations

import argparse
import json
import os
import urllib.error
import urllib.request
from typing import Mapping

from .models import MCFError

DEFAULT_TIMEOUT_SECONDS = 20


def _token() -> str:
    value = os.environ.get("YATL_NODE_TOKEN", "")
    if not value:
        raise MCFError("YATL_NODE_TOKEN is required")
    return value


def _url(base: str, path: str) -> str:
    if not isinstance(base, str) or not base.startswith("https://"):
        raise MCFError("coordinator URL must use https")
    return base.rstrip("/") + path


def request_json(
    base_url: str,
    path: str,
    *,
    token: str,
    method: str = "POST",
    body: Mapping[str, object] | None = None,
    node_id: str | None = None,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> dict:
    if not token:
        raise MCFError("missing coordinator bearer token")
    payload = None if body is None else json.dumps(
        dict(body), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    headers = {
        "authorization": f"Bearer {token}",
        "accept": "application/json",
    }
    if payload is not None:
        headers["content-type"] = "application/json"
    if node_id is not None:
        headers["x-yatl-node"] = node_id
    req = urllib.request.Request(
        _url(base_url, path),
        data=payload,
        headers=headers,
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            raw = response.read()
            if response.status < 200 or response.status >= 300:
                raise MCFError(f"coordinator HTTP status {response.status}")
    except urllib.error.HTTPError as exc:
        raw = exc.read()
        try:
            detail = json.loads(raw)
        except (ValueError, TypeError):
            detail = {"status": f"HTTP_{exc.code}"}
        raise MCFError(f"coordinator rejected request: {detail.get('status', exc.code)}") from exc
    except urllib.error.URLError as exc:
        raise MCFError(f"coordinator unavailable: {exc.reason}") from exc
    try:
        doc = json.loads(raw)
    except (ValueError, TypeError) as exc:
        raise MCFError("coordinator returned non-JSON response") from exc
    if not isinstance(doc, dict) or not isinstance(doc.get("status"), str):
        raise MCFError("coordinator returned invalid response")
    return doc


def claim(base_url: str, node_id: str, *, batch_code: str | None = None,
          lease_seconds: int = 900, token: str | None = None) -> dict:
    body = {"node_id": node_id, "lease_seconds": lease_seconds}
    if batch_code is not None:
        body["batch_code"] = batch_code
    return request_json(base_url, "/v1/claim", token=token or _token(), body=body)


def heartbeat(base_url: str, node_id: str, batch_code: str, *,
              lease_seconds: int = 900, token: str | None = None) -> dict:
    return request_json(
        base_url,
        "/v1/heartbeat",
        token=token or _token(),
        body={"node_id": node_id, "batch_code": batch_code, "lease_seconds": lease_seconds},
    )


def release(base_url: str, node_id: str, batch_code: str, *,
            token: str | None = None) -> dict:
    return request_json(
        base_url,
        "/v1/release",
        token=token or _token(),
        body={"node_id": node_id, "batch_code": batch_code},
    )


def ready(base_url: str, node_id: str, batch_code: str, *,
          result_manifest_sha256: str, result_count: int,
          transfer_mode: str = "R2",
          token: str | None = None) -> dict:
    return request_json(
        base_url,
        "/v1/ready",
        token=token or _token(),
        body={
            "node_id": node_id,
            "batch_code": batch_code,
            "result_manifest_sha256": result_manifest_sha256,
            "result_count": result_count,
            "transfer_mode": transfer_mode,
        },
    )


def status(base_url: str, node_id: str, *, token: str | None = None) -> dict:
    return request_json(
        base_url,
        "/v1/status",
        token=token or _token(),
        method="GET",
        body=None,
        node_id=node_id,
    )


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--coordinator-url", required=True)
    parser.add_argument("--node-id", required=True)
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("claim")
    p.add_argument("--batch")
    p.add_argument("--lease-seconds", type=int, default=900)

    p = sub.add_parser("heartbeat")
    p.add_argument("--batch", required=True)
    p.add_argument("--lease-seconds", type=int, default=900)

    p = sub.add_parser("release")
    p.add_argument("--batch", required=True)

    p = sub.add_parser("ready")
    p.add_argument("--batch", required=True)
    p.add_argument("--result-manifest-sha256", required=True)
    p.add_argument("--result-count", type=int, required=True)
    p.add_argument("--transfer-mode", choices=("R2", "DIRECT_PULL"), default="R2")

    sub.add_parser("status")

    args = parser.parse_args(argv)
    try:
        if args.command == "claim":
            result = claim(
                args.coordinator_url, args.node_id,
                batch_code=args.batch, lease_seconds=args.lease_seconds,
            )
        elif args.command == "heartbeat":
            result = heartbeat(
                args.coordinator_url, args.node_id, args.batch,
                lease_seconds=args.lease_seconds,
            )
        elif args.command == "release":
            result = release(args.coordinator_url, args.node_id, args.batch)
        elif args.command == "ready":
            result = ready(
                args.coordinator_url, args.node_id, args.batch,
                result_manifest_sha256=args.result_manifest_sha256,
                result_count=args.result_count,
                transfer_mode=args.transfer_mode,
            )
        elif args.command == "status":
            result = status(args.coordinator_url, args.node_id)
        else:
            raise MCFError("unsupported worker client command")
        print(json.dumps(result, sort_keys=True))
        return 0
    except (MCFError, OSError, ValueError, TypeError) as exc:
        print(json.dumps({"status": "WORKER_CLIENT_BLOCKED", "reason": str(exc)}, sort_keys=True))
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
