import os, json, requests

API_KEY = os.getenv("OPENAI_API_KEY","").strip()
BASE_URL = "https://api.openai.com/v1"

def _headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type": "application/json"}

def count_tokens(model: str, user_prompt: str) -> int:
    # Approximate (no universal count endpoint exposed here)
    return max(1, len(user_prompt)//4)

def generate(model: str, user_prompt: str, system_prompt: str, json_schema: dict,
             max_output_tokens: int = 400, enable_web_search: bool = False):
    sys_default = ("You are a precise researcher/analyst. Return ONLY strict JSON per schema. "
                   "If unsure, mark fields not_found or ambiguous and echo original input values.")
    # Responses API with json_schema
    payload = {
        "model": model,
        "input": [
            {"role":"system","content":[{"type":"text","text": (system_prompt or sys_default)}]},
            {"role":"user","content":[{"type":"text","text": user_prompt}]}
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": { "name": "Record", "schema": json_schema }
        },
        "max_output_tokens": max_output_tokens
    }
    if enable_web_search:
        payload["tools"] = [{"type":"web_search"}]
        payload["tool_choice"] = "auto"

    r = requests.post(f"{BASE_URL}/responses", headers=_headers(), data=json.dumps(payload), timeout=120)
    if r.status_code >= 400:
        # fallback to chat.completions with JSON instruction
        cc = {
            "model": model,
            "messages": [
                {"role":"system", "content": (system_prompt or sys_default) + "\nReturn ONLY valid JSON matching the schema."},
                {"role":"user", "content": user_prompt}
            ],
            "max_tokens": max_output_tokens,
            "temperature": 0
        }
        r2 = requests.post(f"{BASE_URL}/chat/completions", headers=_headers(), data=json.dumps(cc), timeout=120)
        r2.raise_for_status()
        data = r2.json()
        raw = data.get("choices",[{}])[0].get("message",{}).get("content","")
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
        return d["output"][0]["content"][0]["text"]
    except Exception:
        pass
    if "output_text" in d: return d["output_text"]
    try:
        return d["choices"][0]["message"]["content"]
    except Exception:
        pass
    return json.dumps(d)

def _best_effort_json(text: str) -> dict:
    s = text.find("{"); e = text.rfind("}")
    if s!=-1 and e!=-1 and e>s:
        try: return json.loads(text[s:e+1])
        except Exception: pass
    return {"_parse_error":"Could not parse JSON","_raw": text[:2000]}
