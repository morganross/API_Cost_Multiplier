"""
OpenAI FPF payload probe

Goal:
- Build the exact OpenAI Responses API payload using the FPF OpenAI provider adapter
  (FilePromptForge/providers/openai/fpf_openai_main.py) and send it, to compare with
  our internal diagnoser and the FPF batch behavior.

Why:
- Our serialized diagnoser shows grounded 200s. FPF batch previously saw 500s.
- This probe eliminates drift by using FPF's provider.build_payload and fpf_config.yaml.
- It logs headers (redacted), payload, and response (including x-request-id) for escalation.

Usage:
  python -m api_cost_multiplier.tools.openai_fpf_payload_probe \
    --config api_cost_multiplier/FilePromptForge/fpf_config.yaml \
    --env-file api_cost_multiplier/FilePromptForge/.env \
    --model gpt-5-mini \
    --prompt "Identify 3 recent lithium-ion battery breakthroughs and return JSON with title,publisher,date,url." \
    --request-json true \
    --reasoning-effort low

Run twice (request-json true/false) to compare json_schema vs prompt-JSON with tools.

Outputs:
- Writes logs under: api_cost_multiplier/diagnostics/openai_fpf/YYYYMMDD_HHMMSS/
- Each run file contains: meta, request (headers redacted, payload), response, and classification.
"""

from __future__ import annotations

import os
import sys
import json
import uuid
import time
import argparse
import datetime as _dt
from typing import Any, Dict, Optional
from pathlib import Path
import urllib.request
import urllib.error

REPO_ROOT = Path(__file__).resolve().parents[1]  # .../api_cost_multiplier
DIAG_BASE = REPO_ROOT / "diagnostics" / "openai_fpf"

DEFAULT_CONFIG = REPO_ROOT / "FilePromptForge" / "fpf_config.yaml"
DEFAULT_ENV = REPO_ROOT / "FilePromptForge" / ".env"
DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"


def _read_env_file(env_path: Path, key: str = "OPENAI_API_KEY") -> Optional[str]:
    try:
        if env_path.exists():
            with env_path.open("r", encoding="utf-8") as fh:
                for raw in fh:
                    line = (raw or "").strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    if k.strip() == key:
                        return v.strip().strip('\'"')
    except Exception:
        return None
    return None


def load_api_key(env_file: Path) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    api_key = _read_env_file(env_file)
    if api_key:
        return api_key
    raise RuntimeError(f"OPENAI_API_KEY not found in environment or {env_file}")


def now_tag() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: Path, obj: Any) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)


def _classify_error(status: int, body: Dict[str, Any]) -> str:
    try:
        err = body.get("error") if isinstance(body, dict) else None
        if status == 400:
            msg = (err or {}).get("message", "")
            param = (err or {}).get("param", "")
            if "invalid_json_schema" in (err or {}).get("code", "") or "text.format.schema" in str(param):
                return "invalid_json_schema"
            if "not supported" in msg.lower() and "web_search" in msg.lower():
                return "tool_not_supported"
            return "bad_request"
        if status == 401:
            return "unauthorized"
        if status == 403:
            return "forbidden"
        if status == 404:
            return "not_found"
        if status == 409:
            return "conflict"
        if status == 422:
            return "unprocessable"
        if status == 429:
            return "rate_limited"
        if status >= 500:
            return "server_error"
    except Exception:
        pass
    return f"http_{status}"


def _extract_request_id_from_headers(h) -> Optional[str]:
    try:
        if hasattr(h, "get"):
            rid = h.get("x-request-id") or h.get("X-Request-Id")
            if rid:
                return str(rid)
        if hasattr(h, "items"):
            for k, v in h.items():
                if str(k).lower() == "x-request-id":
                    return str(v)
    except Exception:
        pass
    return None


def http_post_json(url: str, payload: Dict[str, Any], headers: Dict[str, str], timeout: int = 180) -> tuple[int, Dict[str, Any], Dict[str, Any], Optional[str]]:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", resp.getcode() if hasattr(resp, "getcode") else 200)
            try:
                body = json.loads(raw)
            except Exception:
                body = {"raw": raw}
            hdrs = {}
            try:
                for k, v in (resp.headers.items() if hasattr(resp, "headers") else resp.info().items()):  # type: ignore
                    hdrs[k] = v
            except Exception:
                hdrs = {}
            rid = _extract_request_id_from_headers(resp.headers if hasattr(resp, "headers") else resp.info())
            return int(status), body, hdrs, rid
    except urllib.error.HTTPError as he:
        status = int(getattr(he, "code", 500) or 500)
        rid = _extract_request_id_from_headers(getattr(he, "headers", None))
        try:
            msg = he.read().decode("utf-8", errors="replace")
        except Exception:
            msg = ""
        try:
            body = json.loads(msg) if msg else {"error": {"message": str(he)}}
        except Exception:
            body = {"error": {"message": msg or str(he)}}
        hdrs = {}
        try:
            for k, v in he.headers.items():  # type: ignore
                hdrs[k] = v
        except Exception:
            hdrs = {}
        return status, body, hdrs, rid
    except Exception as e:
        return 0, {"error": {"message": f"client_exception: {e}"}}, {}, None


def load_yaml(path: Path) -> Dict[str, Any]:
    import yaml  # type: ignore
    with path.open("r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def main():
    parser = argparse.ArgumentParser(description="Probe OpenAI using FPF provider build_payload.")
    parser.add_argument("--config", default=str(DEFAULT_CONFIG), help="Path to FilePromptForge fpf_config.yaml")
    parser.add_argument("--env-file", default=str(DEFAULT_ENV), help="Path to .env holding OPENAI_API_KEY")
    parser.add_argument("--model", default=None, help="Override model to use (fallback to config.yaml)")
    parser.add_argument("--prompt", default="Identify 3 recent lithium-ion battery breakthroughs and return JSON with title,publisher,published_date,url. Use live web search.", help="User prompt")
    parser.add_argument("--request-json", default="true", choices=["true", "false"], help="Whether to request structured outputs (json_schema) (true) or prompt-JSON (false)")
    parser.add_argument("--reasoning-effort", default="low", choices=["low", "medium", "high"], help="Reasoning effort to request")
    parser.add_argument("--timeout", type=int, default=180, help="Request timeout seconds")
    args = parser.parse_args()

    cfg_path = Path(args.config).resolve()
    env_path = Path(args.env_file).resolve()
    out_dir = ensure_dir(DIAG_BASE / now_tag())

    # Prepare cfg dict like FPF expects
    cfg = load_yaml(cfg_path)
    if args.model:
        cfg["model"] = args.model
    if "reasoning" not in cfg:
        cfg["reasoning"] = {}
    cfg["reasoning"]["effort"] = args.reasoning_effort

    # Toggle json semantics per flag
    req_json = (args.request_json.lower() == "true")
    cfg["json"] = req_json

    # Import FPF provider
    sys.path.insert(0, str((REPO_ROOT / "FilePromptForge").resolve()))
    try:
        import providers.openai.fpf_openai_main as fpf_openai  # type: ignore
    except Exception as e:
        print(f"[ERROR] Could not import FPF OpenAI provider: {e}", file=sys.stderr)
        sys.exit(1)

    # Build payload using FPF adapter
    try:
        payload, provider_headers = fpf_openai.build_payload(args.prompt, cfg)
    except Exception as e:
        print(f"[ERROR] FPF build_payload failed: {e}", file=sys.stderr)
        sys.exit(1)

    # Determine endpoint
    try:
        provider_urls = cfg.get("provider_urls") or {}
        endpoint = provider_urls.get("openai") or cfg.get("provider_url") or DEFAULT_ENDPOINT
    except Exception:
        endpoint = DEFAULT_ENDPOINT

    # Build headers (bearer)
    api_key = load_api_key(env_path)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    if isinstance(provider_headers, dict):
        headers.update(provider_headers)

    # Send
    status, body, resp_headers, req_id = http_post_json(endpoint, payload, headers, timeout=args.timeout)
    classification = _classify_error(status, body if isinstance(body, dict) else {})

    # Write log
    rec = {
        "meta": {
            "status": status,
            "classification": classification,
            "x_request_id": req_id,
            "timestamp": _dt.datetime.now().isoformat(),
            "request_json": req_json,
            "reasoning_effort": args.reasoning_effort,
            "model": cfg.get("model"),
            "endpoint": endpoint,
        },
        "request": {
            "headers": {"Authorization": "***REDACTED***", "Content-Type": "application/json"},
            "payload": payload,
        },
        "response": {
            "headers": resp_headers,
            "body": body,
        },
    }
    out_path = out_dir / f"probe_{'json' if req_json else 'prompt'}_{cfg.get('model')}_{uuid.uuid4().hex[:8]}.json"
    write_json(out_path, rec)

    print(f"[PROBE] Wrote {out_path}")
    print(f"[PROBE] Result: status={status} class={classification} x-request-id={req_id}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[PROBE] Interrupted by user.")
        sys.exit(130)
