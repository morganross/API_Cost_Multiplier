"""
OpenAI grounding + structured outputs diagnoser

Purpose:
- Systematically probe why OpenAI evaluation runs failed under:
  - Hosted web search tool (grounding)
  - Reasoning effort
  - Structured Outputs (json_schema) vs prompt-JSON
- Produce a concrete, evidence-backed reason for failures by running a minimal A/B test matrix
  and capturing request IDs, HTTP status, headers, and error bodies.

How it works:
- Sends serialized (non-concurrent) requests to the OpenAI Responses API (/v1/responses)
- Iterates combinations of:
  * model:            e.g., gpt-5-mini (default), optionally gpt-5, gpt-4.1
  * tool type:        web_search_preview (legacy) and web_search (canonical)
  * output mode:      json_schema (Structured Outputs) vs prompt_json (instruction-only JSON)
  * reasoning.effort: low (default for diagnoser; can set high)
- Logs each attempt (payload summary, error classification, x-request-id) to diagnostics/

Usage (examples):
  - Run defaults (gpt-5-mini; both tool names; both output modes; effort=low):
      python -m api_cost_multiplier.tools.openai_grounding_diagnoser

  - Explicit matrix:
      python -m api_cost_multiplier.tools.openai_grounding_diagnoser --models gpt-5-mini gpt-5 --tool-types web_search web_search_preview --modes json_schema prompt_json --efforts low high

  - Single-case reproduction (recommended first step):
      python -m api_cost_multiplier.tools.openai_grounding_diagnoser --models gpt-5-mini --tool-types web_search_preview --modes json_schema --efforts low

API key resolution priority:
- Env var: OPENAI_API_KEY
- Fallback: api_cost_multiplier/FilePromptForge/.env (OPENAI_API_KEY=...)

Outputs:
- Writes JSON logs to: api_cost_multiplier/diagnostics/openai/YYYYMMDD_HHMMSS/
- Prints a summary table with pass/fail counts and classifications.

Note:
- Requests are serialized to avoid concurrency confounders.
- The diagnoser keeps payloads minimal and redacted to avoid leaking sensitive content.
"""

from __future__ import annotations

import os
import sys
import json
import uuid
import time
import argparse
import datetime as _dt
from typing import Any, Dict, List, Optional, Tuple
from pathlib import Path
import urllib.request
import urllib.error


DEFAULT_ENDPOINT = "https://api.openai.com/v1/responses"
# Resolve repo roots and FPF dir robustly across layouts
# - Typical path in this repo: .../api_cost_multiplier/tools/openai_grounding_diagnoser.py
#   So parents[1] -> api_cost_multiplier, parents[2] -> repo root
REPO_ROOT = Path(__file__).resolve().parents[1]  # .../api_cost_multiplier

def _resolve_fpf_dir() -> Path:
    # Prefer api_cost_multiplier/FilePromptForge
    cand1 = REPO_ROOT / "FilePromptForge"
    # Fallback to repo-root/FilePromptForge if project is laid out differently
    cand2 = Path(__file__).resolve().parents[2] / "FilePromptForge"
    if cand1.exists():
        return cand1
    if cand2.exists():
        return cand2
    return cand1  # default

FPF_DIR = _resolve_fpf_dir()
DEFAULT_ENV_PATH = FPF_DIR / ".env"

DIAG_BASE = REPO_ROOT / "diagnostics" / "openai"


def _read_key_from_env_file(env_path: Path, key: str = "OPENAI_API_KEY") -> Optional[str]:
    try:
        if not env_path.exists():
            return None
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


def load_api_key(env_path: Optional[Path] = None) -> str:
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    # Fallback: FPF canonical .env (or provided env path)
    env_file = env_path if env_path is not None else DEFAULT_ENV_PATH
    api_key = _read_key_from_env_file(env_file)
    if api_key:
        return api_key
    raise RuntimeError(f"OPENAI_API_KEY not found in environment or {env_file}")


def now_tag() -> str:
    return _dt.datetime.now().strftime("%Y%m%d_%H%M%S")


def _redact_headers(headers: Dict[str, Any]) -> Dict[str, Any]:
    safe: Dict[str, Any] = {}
    for k, v in (headers or {}).items():
        lk = str(k).lower()
        if lk in ("authorization", "x-api-key"):
            safe[k] = "***REDACTED***"
        else:
            safe[k] = v
    return safe


def _extract_request_id_from_headers(h) -> Optional[str]:
    """
    Attempt to extract request ID (x-request-id) from a urllib response headers object.
    """
    try:
        # h may be http.client.HTTPMessage
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
    """
    Produce a concise classification string based on HTTP status and error payload.
    """
    try:
        err = body.get("error") if isinstance(body, dict) else None
        if status == 400:
            # Try to detect common invalid schema/tool errors
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


def build_payload(
    model: str,
    tool_type: str,
    mode: str,
    effort: str,
    prompt_text: str
) -> Dict[str, Any]:
    """
    Build a minimal Responses API payload that exercises hosted web search + reasoning
    and either Structured Outputs (json_schema) or prompt-JSON.

    Note: To encourage tool usage, we attach light search options when supported.
    """
    # For prompt-JSON mode, prepend a strict instruction
    final_text = prompt_text
    text_block: Optional[Dict[str, Any]] = None

    if mode == "prompt_json":
        json_instr = (
            "Return only a single valid JSON object. Do not include any prose or Markdown fences. "
            "The object must be strictly valid JSON."
        )
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
        raise ValueError(f"Unsupported mode: {mode} (use 'json_schema' or 'prompt_json')")

    tool_cfg: Dict[str, Any] = {"type": tool_type}
    # Encourage tool invocation for gpt-5* by providing context size and optional user location
    if model.startswith("gpt-5"):
        # search_context_size accepted on some gpt-5 variants
        tool_cfg["search_context_size"] = "high"

    payload: Dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "user",
                "content": final_text,
            }
        ],
        "tools": [tool_cfg],
        "tool_choice": "auto",
        "reasoning": {"effort": effort},
        # Keep generation knobs minimal to avoid unknown params
    }
    if text_block:
        payload["text"] = text_block
    return payload


def send_request(api_key: str, payload: Dict[str, Any], endpoint: str = DEFAULT_ENDPOINT, timeout: int = 120) -> Tuple[int, Dict[str, Any], Dict[str, Any], Optional[str]]:
    """
    Send a POST request to the Responses API, return (status, body_json_or_raw_dict, resp_headers_dict, request_id).
    On failure, returns error JSON if present and attempts to extract x-request-id from headers.
    """
    data = json.dumps(payload).encode("utf-8")
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    req = urllib.request.Request(endpoint, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            status = getattr(resp, "status", resp.getcode() if hasattr(resp, "getcode") else 200)
            rid = _extract_request_id_from_headers(resp.headers if hasattr(resp, "headers") else resp.info())
            try:
                body_json = json.loads(raw)
            except Exception:
                body_json = {"raw": raw}
            # Convert response headers to dict
            hdrs = {}
            try:
                for k, v in (resp.headers.items() if hasattr(resp, "headers") else resp.info().items()):  # type: ignore
                    hdrs[k] = v
            except Exception:
                hdrs = {}
            return int(status), body_json, hdrs, rid
    except urllib.error.HTTPError as he:
        # Attempt to read and parse error body
        status = int(getattr(he, "code", 500) or 500)
        rid = _extract_request_id_from_headers(getattr(he, "headers", None))
        try:
            msg = he.read().decode("utf-8", errors="replace")
        except Exception:
            msg = ""
        try:
            body_json = json.loads(msg) if msg else {"error": {"message": str(he)}}
        except Exception:
            body_json = {"error": {"message": msg or str(he)}}
        # Convert headers to dict
        hdrs = {}
        try:
            for k, v in he.headers.items():  # type: ignore
                hdrs[k] = v
        except Exception:
            hdrs = {}
        return status, body_json, hdrs, rid
    except Exception as e:
        return 0, {"error": {"message": f"client_exception: {e}"}}, {}, None


def ensure_dir(p: Path) -> Path:
    p.mkdir(parents=True, exist_ok=True)
    return p


def write_json(path: Path, obj: Any) -> None:
    with path.open("w", encoding="utf-8") as fh:
        json.dump(obj, fh, indent=2, ensure_ascii=False)


def _detect_grounding_like(body: Dict[str, Any]) -> bool:
    """
    Heuristics to detect that grounding/web search actually occurred.
    Similar to FPF's grounding_enforcer heuristics.
    """
    try:
        if not isinstance(body, dict):
            return False
        # Direct tool call evidence
        if isinstance(body.get("tool_calls"), list) and body.get("tool_calls"):
            return True
        if isinstance(body.get("tools"), list) and body.get("tools"):
            return True
        # Outputs with URLs/citations
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
        # String scan fallback
        s = json.dumps(body, ensure_ascii=False)
        if "web_search" in s or "tool_call" in s or "tool_calls" in s:
            return True
        # Gemini-like candidates (won't apply here but harmless)
        cands = body.get("candidates")
        if isinstance(cands, list):
            for cand in cands:
                gm = cand.get("groundingMetadata")
                if isinstance(gm, dict) and gm:
                    return True
        return False
    except Exception:
        return False


def main():
    parser = argparse.ArgumentParser(description="Diagnose OpenAI grounding + JSON failures via a minimal A/B matrix.")
    parser.add_argument("--endpoint", default=DEFAULT_ENDPOINT, help="OpenAI Responses API endpoint")
    parser.add_argument("--models", nargs="+", default=["gpt-5-mini"], help="Models to test")
    parser.add_argument("--tool-types", nargs="+", default=["web_search_preview", "web_search"], help="Tool type names to test")
    parser.add_argument("--modes", nargs="+", default=["json_schema", "prompt_json"], help="Output modes to test")
    parser.add_argument("--efforts", nargs="+", default=["low"], help="Reasoning efforts to test (e.g., low, high)")
    parser.add_argument("--prompt", default="Identify 3 news articles published in the last 24 hours about lithium-ion battery breakthroughs. Return JSON with title, publisher, published_date, and url. You must consult live web results.", help="Prompt to send")
    parser.add_argument("--env-file", default=None, help="Path to .env file containing OPENAI_API_KEY (defaults to FilePromptForge/.env)")
    parser.add_argument("--sleep", type=float, default=2.0, help="Seconds to sleep between requests to avoid bursty traffic")
    parser.add_argument("--tag", default=None, help="Optional tag to include in log directory name")
    args = parser.parse_args()

    try:
        env_path = Path(args.env_file).resolve() if args.env_file else DEFAULT_ENV_PATH
        api_key = load_api_key(env_path)
    except Exception as e:
        print(f"[ERROR] {e}", file=sys.stderr)
        sys.exit(1)

    stamp = now_tag()
    tag = f"_{args.tag}" if args.tag else ""
    out_dir = ensure_dir(DIAG_BASE / f"{stamp}{tag}")

    print(f"[DIAG] Logging to: {out_dir}")

    summary: List[Dict[str, Any]] = []
    case_num = 0

    for model in args.models:
        for tool in args.tool_types:
            for mode in args.modes:
                for effort in args.efforts:
                    case_num += 1
                    uid = uuid.uuid4().hex[:8]
                    case_id = f"{case_num:02d}-{model}-{tool}-{mode}-{effort}-{uid}"
                    print(f"\n[DIAG] Case {case_id}: model={model}, tool={tool}, mode={mode}, effort={effort}")

                    payload = build_payload(
                        model=model,
                        tool_type=tool,
                        mode=mode,
                        effort=effort,
                        prompt_text=args.prompt
                    )

                    status, body, headers, req_id = send_request(api_key, payload, endpoint=args.endpoint, timeout=180)
                    classification = _classify_error(status, body if isinstance(body, dict) else {})
                    grounded = False
                    if status == 200 and isinstance(body, dict):
                        grounded = _detect_grounding_like(body)

                    # Prepare compact record
                    rec: Dict[str, Any] = {
                        "case_id": case_id,
                        "model": model,
                        "tool_type": tool,
                        "mode": mode,
                        "effort": effort,
                        "http_status": status,
                        "classification": classification,
                        "x_request_id": req_id,
                        "grounding_detected": grounded,
                        "timestamp": _dt.datetime.now().isoformat(),
                    }

                    # Write per-case log with redacted headers and payload summary
                    log_obj = {
                        "meta": rec,
                        "request": {
                            "endpoint": args.endpoint,
                            "headers": _redact_headers({"Authorization": f"Bearer {api_key[:4]}..."}),
                            "payload": payload,  # Contains no secrets
                        },
                        "response": {
                            "headers": headers,
                            "body": body,
                        },
                    }
                    log_path = out_dir / f"{case_id}.json"
                    try:
                        write_json(log_path, log_obj)
                        print(f"[DIAG] Wrote {log_path}")
                    except Exception as e:
                        print(f"[WARN] Failed to write log {log_path}: {e}")

                    # User-friendly line
                    print(f"[DIAG] Result: status={status} class={classification} grounded={grounded} x-request-id={req_id}")

                    summary.append(rec)
                    time.sleep(max(0.0, args.sleep))

    # Write summary
    summary_path = out_dir / "summary.json"
    try:
        write_json(summary_path, summary)
        print(f"\n[DIAG] Summary written to {summary_path}")
    except Exception as e:
        print(f"[WARN] Failed to write summary: {e}")

    # Print aggregate counts
    counts: Dict[str, int] = {}
    by_status: Dict[str, int] = {}
    for r in summary:
        cls = r.get("classification")
        st = str(r.get("http_status"))
        counts[cls] = counts.get(cls, 0) + 1
        by_status[st] = by_status.get(st, 0) + 1

    print("\n[DIAG] Aggregate by classification:")
    for k, v in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {k:24s} {v}")

    print("\n[DIAG] Aggregate by HTTP status:")
    for k, v in sorted(by_status.items(), key=lambda kv: (-kv[1], kv[0])):
        print(f"  {k:6s} {v}")

    print("\n[DIAG] Next steps:")
    print("  - Examine per-case logs in the diagnostics folder (check x_request_id, error bodies).")
    print("  - If 500 server_error persists for tool-enabled json_schema, rerun with --modes prompt_json only.")
    print("  - Try swapping tool types (web_search vs web_search_preview) and models (gpt-5, gpt-4.1).")
    print("  - Use x_request_id when escalating to OpenAI support; include payload shape and timestamps.")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n[DIAG] Interrupted by user.")
        sys.exit(130)
