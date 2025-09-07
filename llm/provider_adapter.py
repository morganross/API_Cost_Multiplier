import pathlib
import yaml
from typing import Optional, Tuple, Dict, Any

_provider_db = None

def _load_provider_db() -> dict:
    global _provider_db
    if _provider_db is not None:
        return _provider_db

    _provider_db = {}
    try:
        prov_dir = pathlib.Path(__file__).resolve().parents[1] / "model_registry" / "providers"
        for yf in prov_dir.glob("*.yaml"):
            try:
                d = yaml.safe_load(yf.read_text(encoding="utf-8")) or {}
                for k, v in d.items():
                    key = k.lower()
                    _provider_db.setdefault(key, {"models": {}, "default_param": None})
                    for model_k, model_v in (v or {}).items():
                        api_params = model_v.get("api_params", {}) if isinstance(model_v, dict) else {}
                        context_window = model_v.get("context_window") if isinstance(model_v, dict) else None
                        _provider_db[key]["models"][model_k] = {"api_params": api_params, "context_window": context_window}
            except Exception:
                continue
    except Exception:
        _provider_db = None
    return _provider_db

def get_token_param(provider_name: str, model_name: Optional[str], canonical: str = "max_tokens") -> str:
    """
    Return the provider-specific parameter name to use for the canonical token argument.
    Example: for OpenAI models this will often return "max_completion_tokens".
    """
    db = _load_provider_db()
    alternates = ["max_completion_tokens", "max_tokens", "maxOutputTokens", "max_tokens_to_sample"]
    p = provider_name.lower() if isinstance(provider_name, str) else provider_name
    m = model_name if isinstance(model_name, str) else None

    if db:
        prov = db.get(p, {})
        models = prov.get("models", {})
        if m and m in models:
            api_params = models[m].get("api_params", {}) or {}
            if canonical in api_params:
                return api_params[canonical]
        default_param = prov.get("default_param")
        if default_param:
            return default_param

    # Provider hardcoded fallbacks
    if p in ("openai",):
        return "max_completion_tokens"
    if p in ("google",):
        return "maxOutputTokens"
    if p in ("anthropic",):
        return "max_tokens_to_sample"
    return alternates[0]

def get_context_window(provider_name: str, model_name: Optional[str]) -> Optional[int]:
    """
    Return the model's context_window if known from provider DB, otherwise None.
    """
    db = _load_provider_db()
    p = provider_name.lower() if isinstance(provider_name, str) else provider_name
    m = model_name if isinstance(model_name, str) else None
    if db:
        prov = db.get(p, {})
        models = prov.get("models", {})
        if m and m in models:
            return models[m].get("context_window")
    return None

def build_token_kwargs(provider_name: str, model_name: Optional[str], token_value: int) -> Tuple[Dict[str, int], Optional[int], str]:
    """
    Return a kwargs dict to pass into a provider call containing the appropriate token parameter,
    plus the model's context_window (if available), and the preferred client identifier.
    Example return: ({"max_completion_tokens": 1500}, 300000, "openai_sdk")
    """
    param = get_token_param(provider_name, model_name, "max_tokens")
    ctx = get_context_window(provider_name, model_name)
    p = provider_name.lower() if isinstance(provider_name, str) else provider_name
    # Determine preferred client for this provider
    if p in ("google",):
        preferred_client = "google_genai"
    elif p in ("openai",):
        preferred_client = "openai_sdk"
    elif p in ("anthropic",):
        preferred_client = "anthropic_sdk"
    elif p in ("openrouter",):
        preferred_client = "openrouter"
    else:
        preferred_client = "generic"
    return {param: int(token_value)}, ctx, preferred_client
