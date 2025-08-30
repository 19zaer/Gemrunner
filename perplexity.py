import os, json, requests

API_KEY = os.getenv("PERPLEXITY_API_KEY","").strip()
BASE_URL = "https://api.perplexity.ai"

def _headers():
    return {"Authorization": f"Bearer {API_KEY}", "Content-Type":"application/json"}

def count_tokens(model: str, user_prompt: str) -> int:
    return max(1, len(user_prompt)//4)

def generate(model: str, user_prompt: str, system_prompt: str, json_schema: dict,
             max_output_tokens: int = 400, enable_web_search: bool = True):
    sys_default = ("You are a precise web researcher. Use the internet. "
                   "Return ONLY strict JSON according to the schema; include citations where applicable.")
    payload = {
        "model": model,
        "messages": [
            {"role":"system","content": (system_prompt or sys_default) + "\nReturn ONLY JSON; no markdown."},
            {"role":"user","content": user_prompt}
        ],
        "temperature": 0.0,
        "max_tokens": max_output_tokens,
        "return_citations": True,
        "search_recency_filter": "month",
        "top_p": 1.0
    }
    r = requests.post(f"{BASE_URL}/chat/completions", headers=_headers(), data=json.dumps(payload), timeout=120)
    r.raise_for_status()
    data = r.json()
    raw = data.get("choices",[{}])[0].get("message",{}).get("content","")
    try:
        return json.loads(raw), raw, {"structured": False}
    except Exception:
        return _best_effort_json(raw), raw, {"structured": False}

def _best_effort_json(text: str) -> dict:
    s = text.find("{"); e = text.rfind("}")
    if s!=-1 and e!=-1 and e>s:
        try: return json.loads(text[s:e+1])
        except Exception: pass
    return {"_parse_error":"Could not parse JSON","_raw": text[:2000]}
