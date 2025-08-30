import os, json
from jsonschema import Draft202012Validator

CATALOG_PATH = os.path.join(os.path.dirname(__file__), "models_catalog.json")

def load_models_catalog():
    with open(CATALOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def pick_model_info(provider: str, model: str):
    catalog = load_models_catalog()
    info = catalog.get(provider, {}).get(model)
    if not info:
        raise ValueError(f"Unknown provider/model: {provider}/{model}")
    return info

def estimate_row_cost(provider: str, model: str, input_tokens: int, output_tokens: int,
                      search_calls_per_row: float = 0.0,
                      extra_token_classes: dict | None = None) -> dict:
    info = pick_model_info(provider, model)
    # Treat missing rates as 0.0 — caller should set in models_catalog.json
    input_rate = float(info.get("input_per_m") or 0.0)
    output_rate = float(info.get("output_per_m") or 0.0)
    cost = (input_tokens/1e6) * input_rate + (output_tokens/1e6) * output_rate

    search_component = 0.0
    if provider == "google":
        web = info.get("web_search", {}) or {}
        per_1k = float(web.get("per_1k") or 0.0)
        search_component = (search_calls_per_row / 1000.0) * per_1k
    elif provider in ("openai","anthropic"):
        web = info.get("web_search", {}) or {}
        per_1k = float(web.get("per_1k") or 0.0)
        search_component = (search_calls_per_row / 1000.0) * per_1k
    elif provider == "perplexity":
        if model == "sonar-deep-research":
            per_1k = float(info.get("search_per_1k") or 0.0)
            search_component = (search_calls_per_row / 1000.0) * per_1k
            if extra_token_classes:
                for k in ["citation_tokens", "reasoning_tokens"]:
                    tks = float(extra_token_classes.get(k) or 0.0)
                    rate = float(info.get("citation_per_m" if "citation" in k else "reasoning_per_m") or 0.0)
                    cost += (tks/1e6) * rate
        else:
            fee = float(info.get("request_fee_per_call") or 0.0)
            search_component = fee * max(1.0, search_calls_per_row)

    total = cost + search_component
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "base_model_cost_usd": round(cost, 6),
        "search_component_usd": round(search_component, 6),
        "row_total_usd": round(total, 6)
    }

def validate_json(instance, schema):
    try:
        validator = Draft202012Validator(schema)
        errors = sorted(validator.iter_errors(instance), key=lambda e: e.path)
        if errors:
            return False, [f"{'/'.join([str(p) for p in e.path])}: {e.message}" for e in errors]
        return True, []
    except Exception as e:
        return False, [f"schema/validation error: {e}"]
