"""
OpenAI concurrency stress probe

Purpose:
- Reproduce transient 5xx server_error and tool gating issues by issuing multiple
  concurrent hosted web search calls to the Responses API.
- Vary model, tool type, and output mode (json_schema vs prompt-JSON), and measure:
  - HTTP status distribution (200/400/429/5xx)
  - Grounding actually used (heuristics)
  - Request IDs (for escalation)
- Save all attempts to diagnostics/openai_stress/YYYYMMDD_HHMMSS/

Usage examples:
  # Default: 10 requests, 5 workers, gpt-5-mini, tool web_search, mode json_schema
  python -m api_cost_multiplier.tools.openai_concurrency_stress_probe \
    --env-file api_cost_multiplier/FilePromptForge/.env

  # Heavier: 50 reqs, 10 workers, gpt-5-mini & gpt-5, both tools and both modes
  python -m api_cost_multiplier.tools.openai_concurrency_stress_probe \
    --env-file api_cost_multiplier/FilePromptForge/.env \
    --total 50 --workers 10 \
    --models gpt-5-mini gpt-5 \
    --tool-types web_search web_search_preview \
    --modes json_schema prompt_json

Notes:
- Requests are randomized across parameter grid and executed via a thread pool.
- This does not attempt to bypass rate limits; expect 429 under heavy load.
"""

from __future__ import annotations

import os
import sys
import json
import time
import random
import argparse
import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request
import urllib.error

DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"
REPO_ROOT = Path(__file__).resolve().parents[1]  # .../api_cost_multiplier
DIAG_BASE = REPO_ROOT / "diagnostics" / "openai_stress"


def now_tag() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


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


def _detect_grounding_like(body: Dict[str, Any]) -> bool:
    try:
        if not isinstance(body, dict):
            return False
        if isinstance(body.get("tool_calls"), list) and body.get("tool_calls"):
            return True
        if isinstance(body.get("tools"), list) and body.get("tools"):
            return True
        output = body.get("output") or body.get("outputs")
        if isinstance(output, list):
            for item in output:
                if not isinstance(item, dict):
                    continue
                content = item.get("content") or item.get("contents")
                if isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict):
                            if any(k in c for k in ("source", "url", "link", "href")):
                                return True
                            t = c.get("text")
                            if isinstance(t, str) and ("http://" in t or "https://" in t or "Citation:" in t or "[source]" in t):
                                return True
                        elif isinstance(c, str):
                            if "http://" in c or "https://" in c or "Citation:" in c:
                                return True
        s = json.dumps(body, ensure_ascii=False)
        if "web_search" in s or "tool_call" in s or "tool_calls" in s:
            return True
        return False
    except Exception:
        return False


def build_payload(model: str, tool_type: str, mode: str, prompt_text: str, effort: str = "low") -> Dict[str, Any]:
    final_text = prompt_text
    text_block: Optional[Dict[str, Any]] = None

    if mode == "prompt_json":
        json_instr = ("Return only a single valid JSON object. Do not include any prose or Markdown fences. The object must be strictly valid JSON.")
        final_text = f"{json_instr}\n\n{prompt_text}"
    elif mode == "json_schema":
        text_block = {
            "format": {
                "type": "json_schema",
                "name": "evaluation_result",
                "schema": {
                    "type": "object",
                    "properties": {
                        "evaluations": {
                            "type": "array",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "criterion": {"type": "string"},
                                    "score": {"type": "integer"},
                                    "reason": {"type": "string"},
                                },
                                "required": ["criterion", "score", "reason"],
                                "additionalProperties": True,
                            },
                        },
                        "winner_doc_id": {"type": "string"},
                        "reason": {"type": "string"},
                    },
                    "additionalProperties": True,
                },
                "strict": False,
            }
        }
    else:
        raise ValueError(f"Unsupported mode: {mode}")

    tool_cfg: Dict[str, Any] = {"type": tool_type}
    if model.startswith("gpt-5"):
        tool_cfg["search_context_size"] = "high"

    payload: Dict[str, Any] = {
        "model": model,
        "input": [{"role": "user", "content": final_text}],
        "tools": [tool_cfg],
        "tool_choice": "auto",
        "reasoning": {"effort": effort},
    }
    if text_block:
        payload["text"] = text_block
    return payload


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


def worker(case_id: str, endpoint: str, headers: Dict[str, str], params: Dict[str, Any], out_dir: Path, timeout: int) -> Dict[str, Any]:
    status, body, resp_headers, req_id = http_post_json(endpoint, params["payload"], headers, timeout=timeout)
    grounded = (status == 200 and _detect_grounding_like(body if isinstance(body, dict) else {}))
    classification = _classify_error(status, body if isinstance(body, dict) else {})

    log = {
        "meta": {
            "case_id": case_id,
            "model": params["model"],
            "tool_type": params["tool_type"],
            "mode": params["mode"],
            "effort": params["effort"],
            "http_status": status,
            "classification": classification,
            "grounding_detected": grounded,
            "x_request_id": req_id,
            "timestamp": _dt.datetime.now().isoformat(),
        },
        "request": {
            "endpoint": endpoint,
            "headers": {"Authorization": "***REDACTED***", "Content-Type": "application/json"},
            "payload": params["payload"],
        },
        "response": {
            "headers": resp_headers,
            "body": body,
        },
    }
    try:
        with (out_dir / f"{case_id}.json").open("w", encoding="utf-8") as fh:
            json.dump(log, fh, indent=2, ensure_ascii=False)
    except Exception:
        pass
    return log


def main():
    parser = argparse.ArgumentParser(description="Stress test OpenAI hosted web search with structured outputs.")
    parser.add_argument("--env-file", required=True, help="Path to .env containing OPENAI_API_KEY")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="Responses API endpoint")
    parser.add_argument("--models", nargs="+", default=["gpt-5-mini"], help="Models to test")
    parser.add_argument("--tool-types", nargs="+", default=["web_search"], help="Tool types: web_search, web_search_preview")
    parser.add_argument("--modes", nargs="+", default=["json_schema"], help="Output modes: json_schema, prompt_json")
    parser.add_argument("--effort", default="low", choices=["low", "medium", "high"], help="Reasoning effort")
    parser.add_argument("--prompt", default="Identify 3 current news articles about lithium-ion breakthroughs and return JSON with title,publisher,published_date,url.", help="Prompt text")
    parser.add_argument("--total", type=int, default=10, help="Total requests")
    parser.add_argument("--workers", type=int, default=5, help="Concurrent workers")
    parser.add_argument("--timeout", type=int, default=180, help="Request timeout")
    args = parser.parse_args()

    api_key = load_api_key(Path(args.env_file).resolve())
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    out_dir = ensure_dir(DIAG_BASE / now_tag())
    print(f"[STRESS] Logging to: {out_dir}")

    # Prepare param grid and randomize
    grid: List[Tuple[str, str, str]] = []
    for m in args.models:
        for t in args.tool_types:
            for mode in args.modes:
                grid.append((m, t, mode))
    random.shuffle(grid)

    # Prepare cases
    cases: List[Tuple[str, Dict[str, Any]]] = []
    for i in range(args.total):
        model, tool_type, mode = grid[i % len(grid)]
        payload = build_payload(model=model, tool_type=tool_type, mode=mode, prompt_text=args.prompt, effort=args.effort)
        case_id = f"{i+1:03d}-{model}-{tool_type}-{mode}-{int(time.time()*1000)%100000}"
        cases.append((case_id, {"model": model, "tool_type": tool_type, "mode": mode, "effort": args.effort, "payload": payload}))

    # Execute with thread pool
    results: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as ex:
        futs = [ex.submit(worker, case_id, args.endpoint, headers, params, out_dir, args.timeout) for case_id, params in cases]
        for fut in as_completed(futs):
            try:
                log = fut.result()
                results.append(log)
                meta = log.get("meta", {})
                print(f"[STRESS] {meta.get('case_id')} status={meta.get('http_status')} class={meta.get('classification')} grounded={meta.get('grounding_detected')} x-request-id={meta.get('x_request_id')}")
            except Exception as e:
                print(f"[STRESS] worker exception: {e}")

    # Aggregate
    counts: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    grounded_ok = 0
    for r in results:
        cls = r.get("meta", {}).get("classification")
        st = str(r.get("meta", {}).get("http_status"))
        counts[cls] = counts.get(cls, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1
        if r.get("meta", {}).get("http_status") == 200 and r.get("meta", {}).get("grounding_detected"):
            grounded_ok += 1

    summary = {
        "totals": len(results),
        "by_classification": counts,
        "by_http_status": by_status,
        "grounded_200": grounded_ok,
        "timestamp": _dt.datetime.now().isoformat(),
        "args": vars(args),
    }
    try:
        with (out_dir / "summary.json").open("w", encoding="utf-8") as fh:
            json.dump(summary, fh, indent=2, ensure_ascii=False)
        print(f"[STRESS] Summary written to {out_dir / 'summary.json'}")
    except Exception as e:
        print(f"[STRESS] Failed to write summary: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[STRESS] Interrupted by user.")
        sys.exit(130)
