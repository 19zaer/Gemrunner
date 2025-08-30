import os, re, json
import pandas as pd
from urllib.parse import urlparse

def parse_file(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path, dtype=str).fillna("")
    elif ext in [".xlsx", ".xls"]:
        df = pd.read_excel(path, dtype=str).fillna("")
    else:
        raise ValueError("Unsupported file type")
    sample = df.iloc[0].to_dict() if len(df) else {}
    return df, sample

def infer_headers(df):
    return list(df.columns)

def read_all_rows(path: str):
    ext = os.path.splitext(path)[1].lower()
    if ext == ".csv":
        df = pd.read_csv(path, dtype=str).fillna("")
    else:
        df = pd.read_excel(path, dtype=str).fillna("")
    return [dict(row) for _, row in df.iterrows()]

def render_prompt_for_row(template: str, row: dict) -> str:
    def repl(m):
        key = m.group(1).strip()
        return str(row.get(key, m.group(0)))
    return re.sub(r"\{\{([^}]+)\}\}", repl, template)

def flatten_json_record(obj, parent_key="", sep="__"):
    items = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            new_key = f"{parent_key}{sep}{k}" if parent_key else k
            if isinstance(v, dict):
                items.extend(flatten_json_record(v, new_key, sep=sep).items())
            elif isinstance(v, list):
                try:
                    items.append((new_key, json.dumps(v, ensure_ascii=False)))
                except Exception:
                    items.append((new_key, str(v)))
            else:
                items.append((new_key, v))
    else:
        items.append((parent_key or "value", obj))
    return dict(items)

def normalize_domain(url: str) -> str:
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return url.strip().lower()
        return parsed.netloc.lower()
    except Exception:
        return url.strip().lower()
