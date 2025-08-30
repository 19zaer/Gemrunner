import os, json, requests

API_KEY = os.getenv("ANTHROPIC_API_KEY","").strip()
BASE_URL = "https://api.anthropic.com/v1"

def _headers():
    return {
        "x-api-key": API_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json"
    }

def count_tokens(model: str, user_prompt: str) -> int:
    return max(1, len(user_prompt)//4)

def generate(model: str, user_prompt: str, system_prompt: str, json_schema: dict,
             max_output_tokens: int = 400, enable_web_search: bool = False):
    sys_default = ("You are a careful analyst. Use web search when allowed. "
                   "Return ONLY strict JSON per schema; no prose.")
    payload = {
        "model": model,
        "system": system_prompt or sys_default,
        "max_tokens": max_output_tokens,
        "messages": [
            {"role":"user","content":[{"type":"text","text": user_prompt}]}
        ],
        "response_format": {"type":"json_schema", "json_schema":{"name":"Record","schema": json_schema}},
        "temperature": 0
    }
    if enable_web_search:
        payload["tools"] = [{"type":"web_search"}]
        payload["tool_choice"] = {"type":"auto"}

    r = requests.post(f"{BASE_URL}/messages", headers=_headers(), data=json.dumps(payload), timeout=120)
    if r.status_code >= 400:
        cc = {
            "model": model,
            "system": (system_prompt or sys_default) + "\nReturn ONLY valid JSON matching the provided schema.",
            "max_tokens": max_output_tokens,
            "messages": [{"role":"user","content":[{"type":"text","text": user_prompt}]}],
            "temperature": 0
        }
        r2 = requests.post(f"{BASE_URL}/messages", headers=_headers(), data=json.dumps(cc), timeout=120)
        r2.raise_for_status()
        data = r2.json()
        raw = _extract_text(data)
        try:
            return json.loads(raw), raw, {"structured": False}
        except Exception:
            return _best_effort_json(raw), raw, {"structured": False}

    data = r.json()
    raw = _extract_text(data)
    try:
        return json.loads(raw), raw, {"structured": True}
    except Exception:
        return _best_effort_json(raw), raw, {"structured": False}

def _extract_text(d: dict) -> str:
    try:
        for blk in d["content"]:
            if blk.get("type") == "text":
                return blk.get("text","")
    except Exception:
        pass
    return json.dumps(d)

def _best_effort_json(text: str) -> dict:
    s = text.find("{"); e = text.rfind("}")
    if s!=-1 and e!=-1 and e>s:
        try: return json.loads(text[s:e+1])
        except Exception: pass
    return {"_parse_error":"Could not parse JSON","_raw": text[:2000]}
