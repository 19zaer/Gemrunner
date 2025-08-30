import os, json, requests

API_KEY = os.getenv("GEMINI_API_KEY","").strip()
BASE_URL = "https://generativelanguage.googleapis.com/v1beta"

def _headers():
    return {"Content-Type":"application/json; charset=utf-8","x-goog-api-key": API_KEY}

def count_tokens(model: str, user_prompt: str) -> int:
    url = f"{BASE_URL}/models/{model}:countTokens"
    payload = {"contents":[{"role":"user","parts":[{"text": user_prompt}]}]}
    r = requests.post(url, headers=_headers(), data=json.dumps(payload), timeout=60)
    r.raise_for_status()
    data = r.json()
    return int(data.get("totalTokens") or data.get("total_tokens") or data.get("promptTokenCount") or 0)

def generate(model: str, user_prompt: str, system_prompt: str, json_schema: dict,
             max_output_tokens: int = 400, enable_web_search: bool = False):
    tools = None
    if enable_web_search:
        tools = [{"google_search": {}}, {"google_search_retrieval": {}}]

    variants = [
        {"generationConfig":{
            "responseMimeType":"application/json",
            "responseSchema": json_schema,
            "maxOutputTokens": max_output_tokens
        }},
        {"generationConfig":{
            "response_mime_type":"application/json",
            "response_schema": json_schema,
            "max_output_tokens": max_output_tokens
        }},
    ]
    sys_default = ("You are a cautious web researcher. Seek proof. Use reputable sources. "
                   "Return ONLY strict JSON matching the schema. Echo original values for unverifiable fields.")

    for cfg in variants:
        payload = {
            "systemInstruction": {"parts": [{"text": (system_prompt or sys_default)}]},
            "contents": [{"role":"user","parts":[{"text": user_prompt}]}]
        }
        payload.update(cfg)
        if tools: payload["tools"] = tools
        url = f"{BASE_URL}/models/{model}:generateContent"
        r = requests.post(url, headers=_headers(), data=json.dumps(payload), timeout=120)
        if r.status_code < 300:
            raw = _extract_text(r.json())
            try:
                return json.loads(raw), raw, {"structured": True}
            except Exception:
                pass

    payload = {
        "systemInstruction": {"parts":[{"text": (system_prompt or sys_default) + "\nReturn ONLY valid JSON."}]},
        "contents":[{"role":"user","parts":[{"text": user_prompt}]}],
        "generationConfig":{"maxOutputTokens": max_output_tokens}
    }
    if tools: payload["tools"] = tools
    url = f"{BASE_URL}/models/{model}:generateContent"
    r = requests.post(url, headers=_headers(), data=json.dumps(payload), timeout=120)
    r.raise_for_status()
    raw = _extract_text(r.json())
    try:
        return json.loads(raw), raw, {"structured": False}
    except Exception:
        return _best_effort_json(raw), raw, {"structured": False}

def _extract_text(resp_json: dict) -> str:
    try:
        return resp_json["candidates"][0]["content"]["parts"][0]["text"]
    except Exception:
        pass
    if "output_text" in resp_json: return resp_json["output_text"]
    return json.dumps(resp_json)

def _best_effort_json(text: str) -> dict:
    s = text.find("{"); e = text.rfind("}")
    if s!=-1 and e!=-1 and e>s:
        try: return json.loads(text[s:e+1])
        except Exception: pass
    return {"_parse_error":"Could not parse JSON","_raw": text[:2000]}
