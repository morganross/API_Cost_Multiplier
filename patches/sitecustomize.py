"""
sitecustomize.py

Purpose:
- Hard-disable provider-side streaming (OpenAI SSE) while preserving normal console/stdout logging.
- No edits to vendor (gpt-researcher) code. This module is auto-imported if on sys.path.

Strategy:
- Ensure GPTR_DISABLE_STREAMING is set to "true".
- Monkeypatch OpenAI SDK resource methods to strip/ignore `stream=True`:
  * chat.completions.create (sync + async)
  * responses.create (sync + async)
  * responses.stream (sync + async) -> degrade to non-stream create
"""
from __future__ import annotations

import os

# Signal-based guard (honored by some stacks)
os.environ.setdefault("GPTR_DISABLE_STREAMING", "true")

try:
    # OpenAI Python SDK non-stream enforcement (covers v1.x resources and v0.x legacy)
    from functools import wraps
    import time, json, random

    # Shim helpers for emulating OpenAI streaming when callers expect a context manager
    class _ShimDelta:
        def __init__(self, content, role="assistant"):
            self.content = content
            self.role = role

    class _ShimChoice:
        def __init__(self, content):
            self.delta = _ShimDelta(content)
            self.index = 0
            self.finish_reason = "stop"

    class _ShimChunk:
        def __init__(self, content, model=None):
            # Minimal fields commonly present on OpenAI ChatCompletionChunk
            self.id = f"shim-{int(time.time()*1000)}-{random.randint(1000,9999)}"
            self.object = "chat.completion.chunk"
            self.created = int(time.time())
            self.model = model or os.environ.get("SMART_LLM") or os.environ.get("FAST_LLM") or os.environ.get("STRATEGIC_LLM") or ""
            self.choices = [_ShimChoice(content)]

        # Emulate OpenAI pydantic model API used by downstream code
        def model_dump(self, *args, **kwargs):
            try:
                return {
                    "id": self.id,
                    "object": self.object,
                    "created": self.created,
                    "model": self.model,
                    "choices": [
                        {
                            "delta": {
                                "role": getattr(self.choices[0].delta, "role", "assistant"),
                                "content": getattr(self.choices[0].delta, "content", "")
                            },
                            "index": getattr(self.choices[0], "index", 0),
                            "finish_reason": getattr(self.choices[0], "finish_reason", "stop"),
                        }
                    ]
                }
            except Exception:
                # Safe fallback
                return {
                    "id": getattr(self, "id", "shim"),
                    "object": getattr(self, "object", "chat.completion.chunk"),
                    "created": getattr(self, "created", int(time.time())),
                    "model": getattr(self, "model", ""),
                    "choices": [{"delta": {"role": "assistant", "content": ""}, "index": 0, "finish_reason": "stop"}]
                }

        def model_dump_json(self, *args, **kwargs):
            try:
                return json.dumps(self.model_dump())
            except Exception:
                return "{}"

    class StreamShim:
        def __init__(self, text):
            self._text = text or ""

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

        def __iter__(self):
            # Yield a single chunk shaped like OpenAI ChatCompletionChunk
            yield _ShimChunk(self._text)

    class AsyncStreamShim:
        def __init__(self, text):
            self._text = text or ""

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, tb):
            return False

        def __aiter__(self):
            async def gen():
                yield _ShimChunk(self._text)
            return gen()

    def _extract_text_from_chat_completion(resp):
        try:
            return getattr(resp.choices[0].message, "content", None)
        except Exception:
            try:
                return resp.choices[0].delta.content
            except Exception:
                return str(resp)

    def _strip_stream_from_kwargs(kwargs):
        if not isinstance(kwargs, dict):
            return
        # remove top-level stream
        kwargs.pop("stream", None)
        # remove nested indications
        body = kwargs.get("json") or kwargs.get("data") or kwargs.get("body") or {}
        if isinstance(body, dict):
            body.pop("stream", None)
        extra_body = kwargs.get("extra_body")
        if isinstance(extra_body, dict):
            extra_body.pop("stream", None)

    def _map_token_params(kwargs, path):
        """
        Normalize token parameter names and apply conservative model caps.
        - For OpenAI responses endpoint (/v1/responses): map max_tokens -> max_completion_tokens.
        - Cap tokens for known models (e.g., gpt-4o <= 16384) to avoid 400s.
        """
        try:
            body = kwargs.get("json") or kwargs.get("data") or kwargs.get("body")
            if not isinstance(body, dict):
                return
            model = str(body.get("model") or "")
            # Model caps (extend as needed)
            cap = 16384 if "gpt-4o" in model else None
            is_responses = isinstance(path, str) and "/responses" in path

            # If using responses API, prefer max_completion_tokens
            if is_responses:
                if "max_tokens" in body:
                    try:
                        val = int(body.get("max_tokens") or 0)
                    except Exception:
                        val = body.get("max_tokens")
                        try:
                            val = int(val)
                        except Exception:
                            val = 0
                    if cap is not None and isinstance(val, int) and val > 0:
                        val = min(val, cap)
                    body["max_completion_tokens"] = val
                    body.pop("max_tokens", None)
                elif "max_completion_tokens" in body:
                    try:
                        val = int(body.get("max_completion_tokens") or 0)
                        if cap is not None and val > 0:
                            body["max_completion_tokens"] = min(val, cap)
                    except Exception:
                        pass
            else:
                # Non-responses endpoints: keep original name but cap if present
                if "max_tokens" in body:
                    try:
                        val = int(body.get("max_tokens") or 0)
                        if cap is not None and val > 0:
                            body["max_tokens"] = min(val, cap)
                    except Exception:
                        pass

            # Write back to the original container key to ensure effect
            if "json" in kwargs and isinstance(kwargs["json"], dict):
                kwargs["json"] = body
            elif "data" in kwargs and isinstance(kwargs["data"], dict):
                kwargs["data"] = body
            elif "body" in kwargs and isinstance(kwargs["body"], dict):
                kwargs["body"] = body
        except Exception:
            # best-effort; never break requests
            pass

    # Patch low-level request for v1.x to ensure no SSE headers or stream flags leak through
    try:
        from openai._base_client import SyncAPIClient as _SyncClient, AsyncAPIClient as _AsyncClient  # type: ignore

        _orig_sync_request = _SyncClient.request

        @wraps(_orig_sync_request)
        def _sync_request_no_stream(self, method, path, **kwargs):
            _strip_stream_from_kwargs(kwargs)
            # Force non-stream at call level
            kwargs["stream"] = False
            # Normalize token params and apply model caps where appropriate
            _map_token_params(kwargs, path)
            # Drop unexpected 'headers' kwarg to match client signature
            if "headers" in kwargs:
                headers = kwargs.pop("headers") or {}
                if isinstance(headers, dict):
                    accept = headers.get("Accept") or headers.get("accept")
                    if accept and "text/event-stream" in accept:
                        # Intentionally discard SSE Accept; no re-injection
                        pass
            return _orig_sync_request(self, method, path, **kwargs)

        _SyncClient.request = _sync_request_no_stream

        _orig_async_request = _AsyncClient.request

        @wraps(_orig_async_request)
        async def _async_request_no_stream(self, method, path, **kwargs):
            _strip_stream_from_kwargs(kwargs)
            kwargs["stream"] = False
            # Normalize token params and apply model caps where appropriate
            _map_token_params(kwargs, path)
            # Drop unexpected 'headers' kwarg to match client signature
            if "headers" in kwargs:
                headers = kwargs.pop("headers") or {}
                if isinstance(headers, dict):
                    accept = headers.get("Accept") or headers.get("accept")
                    if accept and "text/event-stream" in accept:
                        # Intentionally discard SSE Accept; no re-injection
                        pass
            return await _orig_async_request(self, method, path, **kwargs)

        _AsyncClient.request = _async_request_no_stream
    except Exception:
        pass

    # v1.x resource layer (still helpful if request patch is bypassed by some code paths)
    try:
        from openai.resources.chat.completions import Completions as _ChatCompletions  # type: ignore
        _orig_cc_create = _ChatCompletions.create

        @wraps(_orig_cc_create)
        def _cc_create_nonstream(self, *args, **kwargs):
            # If caller requested stream=True, return a context-manager shim
            want_stream = False
            if "stream" in kwargs and kwargs["stream"]:
                want_stream = True
                kwargs["stream"] = False
            _strip_stream_from_kwargs(kwargs)
            result = _orig_cc_create(self, *args, **kwargs)
            if want_stream:
                text = _extract_text_from_chat_completion(result)
                return StreamShim(text)
            return result

        _ChatCompletions.create = _cc_create_nonstream
    except Exception:
        pass

    try:
        from openai.resources.chat.completions import AsyncCompletions as _AsyncChatCompletions  # type: ignore
        _orig_acc_create = _AsyncChatCompletions.create

        async def _acc_create_nonstream(self, *args, **kwargs):
            # If caller requested stream=True, return an async context-manager shim
            want_stream = False
            if "stream" in kwargs and kwargs["stream"]:
                want_stream = True
                kwargs["stream"] = False
            _strip_stream_from_kwargs(kwargs)
            result = await _orig_acc_create(self, *args, **kwargs)
            if want_stream:
                text = _extract_text_from_chat_completion(result)
                return AsyncStreamShim(text)
            return result

        _AsyncChatCompletions.create = _acc_create_nonstream
    except Exception:
        pass

    try:
        from openai.resources.responses import Responses as _Responses  # type: ignore
        _orig_resp_create = _Responses.create

        @wraps(_orig_resp_create)
        def _resp_create_nonstream(self, *args, **kwargs):
            _strip_stream_from_kwargs(kwargs)
            return _orig_resp_create(self, *args, **kwargs)

        if hasattr(_Responses, "stream"):
            _orig_resp_stream = _Responses.stream

            @wraps(_orig_resp_stream)
            def _resp_stream_degraded(self, *args, **kwargs):
                _strip_stream_from_kwargs(kwargs)
                return _resp_create_nonstream(self, *args, **kwargs)

            _Responses.stream = _resp_stream_degraded  # type: ignore[attr-defined]
        _Responses.create = _resp_create_nonstream
    except Exception:
        pass

    try:
        from openai.resources.responses import AsyncResponses as _AsyncResponses  # type: ignore
        _orig_aresp_create = _AsyncResponses.create

        async def _aresp_create_nonstream(self, *args, **kwargs):
            _strip_stream_from_kwargs(kwargs)
            return await _orig_aresp_create(self, *args, **kwargs)

        if hasattr(_AsyncResponses, "stream"):
            _orig_aresp_stream = _AsyncResponses.stream

            async def _aresp_stream_degraded(self, *args, **kwargs):
                _strip_stream_from_kwargs(kwargs)
                return await _aresp_create_nonstream(self, *args, **kwargs)

            _AsyncResponses.stream = _aresp_stream_degraded  # type: ignore[attr-defined]
        _AsyncResponses.create = _aresp_create_nonstream
    except Exception:
        pass

    # Legacy v0.x APIRequestor request hooks (older openai client)
    try:
        import openai as _openai  # type: ignore
        # Patch APIRequestor if present (v0.x style)
        try:
            from openai import api_requestor as _api_requestor  # type: ignore
            if hasattr(_api_requestor, "APIRequestor"):
                _APIRequestor = _api_requestor.APIRequestor

                # sync
                if hasattr(_APIRequestor, "request"):
                    _orig_api_req = _APIRequestor.request

                    @wraps(_orig_api_req)
                    def _api_request_no_stream(self, method, url, *args, **kwargs):
                        # args in v0.x are often (params, headers, stream, request_id, request_timeout)
                        # Normalize kwargs where possible
                        if len(args) >= 3:
                            # override the positional "stream" arg to False if present
                            params, headers, stream_flag = args[0], args[1], args[2]
                            if isinstance(headers, dict):
                                acc = headers.get("Accept") or headers.get("accept")
                                if acc and "text/event-stream" in acc:
                                    headers["Accept"] = "application/json"
                                    headers.pop("accept", None)
                            if stream_flag:
                                args = (params, headers, False) + args[3:]
                        if "stream" in kwargs:
                            kwargs["stream"] = False
                        return _orig_api_req(self, method, url, *args, **kwargs)

                    _APIRequestor.request = _api_request_no_stream  # type: ignore[attr-defined]

                # async
                if hasattr(_APIRequestor, "arequest"):
                    _orig_api_areq = _APIRequestor.arequest

                    @wraps(_orig_api_areq)
                    async def _api_arequest_no_stream(self, method, url, *args, **kwargs):
                        if len(args) >= 3:
                            params, headers, stream_flag = args[0], args[1], args[2]
                            if isinstance(headers, dict):
                                acc = headers.get("Accept") or headers.get("accept")
                                if acc and "text/event-stream" in acc:
                                    headers["Accept"] = "application/json"
                                    headers.pop("accept", None)
                            if stream_flag:
                                args = (params, headers, False) + args[3:]
                        if "stream" in kwargs:
                            kwargs["stream"] = False
                        return await _orig_api_areq(self, method, url, *args, **kwargs)

                    _APIRequestor.arequest = _api_arequest_no_stream  # type: ignore[attr-defined]
        except Exception:
            pass

        # Legacy ChatCompletion convenience (v0.x)
        if hasattr(_openai, "ChatCompletion"):
            _legacy_cc = _openai.ChatCompletion

            if hasattr(_legacy_cc, "create"):
                _legacy_create = _legacy_cc.create

                @wraps(_legacy_create)
                def _legacy_create_nonstream(*args, **kwargs):
                    _strip_stream_from_kwargs(kwargs)
                    return _legacy_create(*args, **kwargs)

                _legacy_cc.create = _legacy_create_nonstream  # type: ignore[attr-defined]

            if hasattr(_legacy_cc, "acreate"):
                _legacy_acreate = _legacy_cc.acreate

                async def _legacy_acreate_nonstream(*args, **kwargs):
                    _strip_stream_from_kwargs(kwargs)
                    return await _legacy_acreate(*args, **kwargs)

                _legacy_cc.acreate = _legacy_acreate_nonstream  # type: ignore[attr-defined]
    except Exception:
        pass

except Exception:
    # Fail-safe: never break the host application if the OpenAI non-stream patches cannot be applied.
    pass

# Stream shim for GPT-Researcher: degrade streaming to non-stream + simulate chunking
try:
    from gpt_researcher.gpt_researcher.llm_provider.generic.base import GenericLLMProvider as _GR_Generic  # type: ignore

    if hasattr(_GR_Generic, "stream_response"):
        _orig_stream_response = _GR_Generic.stream_response

        async def _shim_stream_response(self, messages, websocket=None, **kwargs):
            """
            Replacement for GenericLLMProvider.stream_response that avoids provider-side streaming.
            It performs a single ainvoke(), then simulates chunked streaming by emitting linewise output.
            Returns the full response string, preserving the original method contract.
            """
            response_text = ""
            try:
                # Single-shot non-stream call via LangChain Chat model
                output = await self.llm.ainvoke(messages, **kwargs)
                response_text = getattr(output, "content", None)
                if isinstance(response_text, list):
                    # Join structured content blocks defensively
                    try:
                        response_text = "".join(
                            [part.get("text", "") if isinstance(part, dict) else str(part) for part in response_text]
                        )
                    except Exception:
                        response_text = "".join([str(part) for part in response_text])
                if response_text is None:
                    response_text = str(output)
            except Exception:
                # Fallback to original behavior (best-effort)
                return await _orig_stream_response(self, messages, websocket=websocket, **kwargs)

            # Simulate streaming output by sending linewise chunks for logs/websocket
            paragraph = ""
            for ch in response_text:
                paragraph += ch
                if ch == "\n":
                    try:
                        await self._send_output(paragraph, websocket)
                    except Exception:
                        pass
                    paragraph = ""

            if paragraph:
                try:
                    await self._send_output(paragraph, websocket)
                except Exception:
                    pass

            return response_text

        _GR_Generic.stream_response = _shim_stream_response  # type: ignore[attr-defined]
except Exception:
    # If GPT-Researcher is not importable yet, skip silently
    pass

# Hard-disable streaming at GPT-Researcher llm.create_chat_completion entrypoint
# This avoids downstream libraries expecting an async streaming context.
try:
    from gpt_researcher.gpt_researcher.utils import llm as _GR_llm  # type: ignore

    if hasattr(_GR_llm, "create_chat_completion"):
        _orig_gr_create_chat_completion = _GR_llm.create_chat_completion

        async def _create_chat_completion_no_stream(
            messages,
            model=None,
            temperature=0.4,
            max_tokens=4000,
            llm_provider=None,
            stream=False,
            websocket=None,
            llm_kwargs=None,
            cost_callback=None,
            reasoning_effort=None,
            **kwargs
        ):
            # Force non-streaming behavior and disable websocket streaming expectations
            stream = False
            websocket = None
            return await _orig_gr_create_chat_completion(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                llm_provider=llm_provider,
                stream=stream,
                websocket=websocket,
                llm_kwargs=llm_kwargs,
                cost_callback=cost_callback,
                reasoning_effort=reasoning_effort,
                **kwargs
            )

        _GR_llm.create_chat_completion = _create_chat_completion_no_stream  # type: ignore[attr-defined]
except Exception:
    # Best-effort; if GPT-Researcher module layout changes, skip silently.
    pass

# Redundant patching for alternate import paths (module alias safety)
# Some code imports modules as `gpt_researcher.utils.llm` while others use
# `gpt_researcher.gpt_researcher.utils.llm`. Patch both to ensure coverage.
try:
    # Patch GenericLLMProvider.get_chat_response and .stream_response for alias path
    from gpt_researcher.llm_provider.generic.base import GenericLLMProvider as _GR_Generic_Alias  # type: ignore

    if hasattr(_GR_Generic_Alias, "get_chat_response"):
        async def _alias_get_chat_response(self, messages, stream, websocket=None, **kwargs):
            # Always perform a single non-stream invocation
            try:
                output = await self.llm.ainvoke(messages, **kwargs)
                text = getattr(output, "content", None)
                if isinstance(text, list):
                    try:
                        text = "".join([p.get("text", "") if isinstance(p, dict) else str(p) for p in text])
                    except Exception:
                        text = "".join([str(p) for p in text])
                if text is None:
                    text = str(output)
            except Exception:
                # Fallback: if ainvoke fails, try original streaming path if present
                try:
                    return await _orig_stream_response_alias(self, messages, websocket=websocket, **kwargs)  # type: ignore[name-defined]
                except Exception:
                    return ""

            # If caller asked for streaming, simulate linewise emission
            if stream:
                buf = ""
                for ch in text:
                    buf += ch
                    if ch == "\n":
                        try:
                            await self._send_output(buf, websocket)
                        except Exception:
                            pass
                        buf = ""
                if buf:
                    try:
                        await self._send_output(buf, websocket)
                    except Exception:
                        pass
            return text

        _GR_Generic_Alias.get_chat_response = _alias_get_chat_response  # type: ignore[attr-defined]

    if hasattr(_GR_Generic_Alias, "stream_response"):
        _orig_stream_response_alias = _GR_Generic_Alias.stream_response

        async def _shim_stream_response_alias(self, messages, websocket=None, **kwargs):
            # Defer to get_chat_response with stream=True to unify behavior
            return await _GR_Generic_Alias.get_chat_response(self, messages, True, websocket=websocket, **kwargs)  # type: ignore[misc]

        _GR_Generic_Alias.stream_response = _shim_stream_response_alias  # type: ignore[attr-defined]
except Exception:
    # Best-effort
    pass

try:
    # Patch utils.llm.create_chat_completion for alias path
    from gpt_researcher.utils import llm as _GR_llm_alias  # type: ignore
    if hasattr(_GR_llm_alias, "create_chat_completion"):
        _orig_alias_cc = _GR_llm_alias.create_chat_completion

        async def _create_chat_completion_no_stream_alias(
            messages,
            model=None,
            temperature=0.4,
            max_tokens=4000,
            llm_provider=None,
            stream=False,
            websocket=None,
            llm_kwargs=None,
            cost_callback=None,
            reasoning_effort=None,
            **kwargs
        ):
            # Force non-streaming behavior regardless of caller flags
            return await _orig_alias_cc(
                messages=messages,
                model=model,
                temperature=temperature,
                max_tokens=max_tokens,
                llm_provider=llm_provider,
                stream=False,
                websocket=None,
                llm_kwargs=llm_kwargs,
                cost_callback=cost_callback,
                reasoning_effort=reasoning_effort,
                **kwargs
            )

        _GR_llm_alias.create_chat_completion = _create_chat_completion_no_stream_alias  # type: ignore[attr-defined]
except Exception:
    # Best-effort
    pass

# Also ensure modules that imported the symbol earlier use the non-stream shim
# by rebinding create_chat_completion inside actions.report_generation modules.
try:
    # Namespaced module path
    from gpt_researcher.gpt_researcher.actions import report_generation as _RG_ns  # type: ignore
    if hasattr(_RG_ns, "create_chat_completion"):
        from gpt_researcher.gpt_researcher.utils import llm as _GR_llm  # type: ignore
        if hasattr(_GR_llm, "create_chat_completion"):
            _RG_ns.create_chat_completion = _GR_llm.create_chat_completion  # type: ignore[attr-defined]
except Exception:
    pass

try:
    # Alias module path
    from gpt_researcher.actions import report_generation as _RG_alias  # type: ignore
    if hasattr(_RG_alias, "create_chat_completion"):
        from gpt_researcher.utils import llm as _GR_llm_alias2  # type: ignore
        if hasattr(_GR_llm_alias2, "create_chat_completion"):
            _RG_alias.create_chat_completion = _GR_llm_alias2.create_chat_completion  # type: ignore[attr-defined]
except Exception:
    pass

# Ensure planner receives a dict even if model returns plain text (prevents AttributeError in editor.plan_research)
try:
    from gpt_researcher.multi_agents.agents.utils import llms as _GR_llms  # type: ignore
    _orig_call_model = _GR_llms.call_model

    async def _call_model_norm(prompt, model, response_format=None):
        """
        Wrapper ensuring JSON-like dict is always returned when planning requires 'json'.
        Falls back to a minimal structure when the model returns plain text.
        """
        from datetime import datetime
        import json, re
        import json_repair

        # Always request JSON from the underlying call
        try:
            res = await _orig_call_model(prompt=prompt, model=model, response_format="json")
        except Exception:
            res = None

        today = datetime.now().strftime('%d/%m/%Y')

        # If already a proper dict
        if isinstance(res, dict):
            title = res.get("title") or "Untitled Plan"
            date_val = res.get("date") or today
            sections = res.get("sections")
            if isinstance(sections, list):
                sections = [str(s).strip() for s in sections if str(s).strip()]
            elif isinstance(sections, str):
                sections = [sections.strip()]
            else:
                sections = ["Initial Research Plan"]
            return {"title": title, "date": date_val, "sections": sections}

        # If list, treat as sections
        if isinstance(res, list):
            sections = [str(s).strip() for s in res if str(s).strip()]
            return {"title": "Untitled Plan", "date": today, "sections": sections[:3] or ["Initial Research Plan"]}

        # If string or None, try to repair JSON from content
        text = "" if res is None else str(res)
        text = text.strip()

        # Try robust JSON repair on the whole text
        try:
            obj = json_repair.loads(text)
            if isinstance(obj, dict):
                t = obj.get("title") or "Untitled Plan"
                d = obj.get("date") or today
                secs = obj.get("sections")
                if isinstance(secs, list):
                    secs = [str(s).strip() for s in secs if str(s).strip()]
                elif isinstance(secs, str):
                    secs = [secs.strip()]
                else:
                    secs = ["Initial Research Plan"]
                return {"title": t, "date": d, "sections": secs}
            if isinstance(obj, list):
                secs = [str(s).strip() for s in obj if str(s).strip()]
                return {"title": "Untitled Plan", "date": today, "sections": secs[:3] or ["Initial Research Plan"]}
        except Exception:
            pass

        # Extract first JSON object/array from text
        m = re.search(r"\{(.|\s)*\}", text)
        if m:
            try:
                obj = json_repair.loads(m.group(0))
                if isinstance(obj, dict):
                    t = obj.get("title") or "Untitled Plan"
                    d = obj.get("date") or today
                    secs = obj.get("sections")
                    if isinstance(secs, list):
                        secs = [str(s).strip() for s in secs if str(s).strip()]
                    elif isinstance(secs, str):
                        secs = [secs.strip()]
                    else:
                        secs = ["Initial Research Plan"]
                    return {"title": t, "date": d, "sections": secs}
                if isinstance(obj, list):
                    secs = [str(s).strip() for s in obj if str(s).strip()]
                    return {"title": "Untitled Plan", "date": today, "sections": secs[:3] or ["Initial Research Plan"]}
            except Exception:
                pass

        m = re.search(r"\[(.|\s)*\]", text)
        if m:
            try:
                arr = json_repair.loads(m.group(0))
                if isinstance(arr, list):
                    secs = [str(s).strip() for s in arr if str(s).strip()]
                    return {"title": "Untitled Plan", "date": today, "sections": secs[:3] or ["Initial Research Plan"]}
            except Exception:
                pass

        # Fallback narrative -> minimal structure
        first_line = next((ln.strip() for ln in text.splitlines() if ln.strip()), "Initial Research Plan")
        title = first_line[:100]
        sections = [first_line] if first_line else ["Initial Research Plan"]
        return {"title": title, "date": today, "sections": sections}

    _GR_llms.call_model = _call_model_norm
except Exception:
    # If module path changes, skip silently
    pass
