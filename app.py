import os, uuid, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from flask import Flask, request, jsonify, send_file, send_from_directory
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

from processing import (
    parse_file, infer_headers, read_all_rows,
    render_prompt_for_row, flatten_json_record, normalize_domain
)
from utils import (
    load_models_catalog, pick_model_info, estimate_row_cost, validate_json
)
from providers import get as get_provider

load_dotenv()

UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "tmp_uploads")
RESULT_DIR = os.path.join(os.path.dirname(__file__), "..", "tmp_results")
os.makedirs(UPLOAD_DIR, exist_ok=True)
os.makedirs(RESULT_DIR, exist_ok=True)

CONCURRENCY = max(1, int(os.getenv("CONCURRENCY", "5")))
MAX_OUTPUT_TOKENS = int(os.getenv("MAX_OUTPUT_TOKENS", "400"))

app = Flask(__name__)
FILES = {}

@app.route("/api/models", methods=["GET"])
def models():
    cat = load_models_catalog()
    rows = []
    for prov, models in cat.items():
        for mid, info in models.items():
            rows.append({
                "provider": prov, "model": mid,
                "display_name": info.get("display_name", mid),
                "input_per_m": info.get("input_per_m"),
                "output_per_m": info.get("output_per_m"),
                "pricing_url": info.get("pricing_url"),
                "notes": info.get("notes", ""),
                "capabilities": info.get("capabilities", []),
                "web_search": info.get("web_search", None),
                "extra": {k:v for k,v in info.items() if k not in ["display_name","input_per_m","output_per_m","pricing_url","notes","capabilities","web_search"]}
            })
    return jsonify({"models": rows})

@app.route("/api/upload", methods=["POST"])
def upload():
    if "file" not in request.files:
        return jsonify({"error":"no file"}), 400
    f = request.files["file"]
    filename = secure_filename(f.filename)
    if not filename:
        return jsonify({"error":"invalid filename"}), 400

    file_id = str(uuid.uuid4())
    ext = os.path.splitext(filename)[1].lower()
    out_path = os.path.join(UPLOAD_DIR, f"{file_id}{ext}")
    f.save(out_path)

    df, sample = parse_file(out_path)
    headers = infer_headers(df)
    n_rows = len(df)
    FILES[file_id] = {"path": out_path, "ext": ext, "headers": headers, "n_rows": n_rows}

    return jsonify({"file_id": file_id, "headers": headers, "n_rows": n_rows, "sample_first_row": sample})

def _render_tasks_from_request(data, first_row):
    """
    Two modes:
      - Single-task: provider, model, prompt_template, json_schema
      - Multi-task: tasks: [{name, provider, model, prompt_template, json_schema, enable_web_search, est_search_calls_per_row}]
    Returns list of tasks with rendered prompts for the given row.
    """
    tasks = data.get("tasks")
    if tasks and isinstance(tasks, list) and len(tasks) > 0:
        out = []
        for t in tasks:
            prompt_template = t.get("prompt_template","")
            out.append({
                "name": t.get("name") or t.get("model"),
                "provider": t.get("provider"),
                "model": t.get("model"),
                "enable_web_search": bool(t.get("enable_web_search", False)),
                "est_search_calls_per_row": float(t.get("est_search_calls_per_row", 1.0)),
                "json_schema": t.get("json_schema"),
                "user_prompt": render_prompt_for_row(prompt_template, first_row),
            })
        return out
    else:
        prompt_template = data.get("prompt_template","")
        return [{
            "name": data.get("task_name","task1"),
            "provider": data.get("provider","google"),
            "model": data.get("model","gemini-2.5-flash"),
            "enable_web_search": bool(data.get("enable_web_search", False)),
            "est_search_calls_per_row": float(data.get("est_search_calls_per_row", 1.0)),
            "json_schema": data.get("json_schema"),
            "user_prompt": render_prompt_for_row(prompt_template, first_row),
        }]

@app.route("/api/estimate", methods=["POST"])
def estimate():
    data = request.get_json(force=True)
    file_id = data.get("file_id")
    if not file_id: return jsonify({"error":"missing file_id"}), 400
    meta = FILES.get(file_id)
    if not meta: return jsonify({"error":"file not found"}), 404

    rows = read_all_rows(meta["path"])
    if not rows: return jsonify({"error":"no rows"}), 400
    first_row = rows[0]

    task_list = _render_tasks_from_request(data, first_row)

    est = []
    total_row = 0.0
    for t in task_list:
        provider = get_provider(t["provider"])
        try:
            tok_in = provider.count_tokens(t["model"], t["user_prompt"])
        except Exception:
            tok_in = max(1, len(t["user_prompt"])//4)

        tok_out = int(data.get("max_output_tokens", os.getenv("MAX_OUTPUT_TOKENS","400")))
        extra = data.get("extra_token_classes", {})
        row_cost = estimate_row_cost(
            t["provider"], t["model"], tok_in, tok_out,
            search_calls_per_row=t.get("est_search_calls_per_row", 0.0),
            extra_token_classes=extra
        )
        total_row += row_cost["row_total_usd"]
        est.append({"task": t["name"], "provider": t["provider"], "model": t["model"], **row_cost})

    n_rows = meta["n_rows"]
    return jsonify({
        "n_rows": n_rows,
        "per_row_total_usd": round(total_row, 6),
        "full_sheet_total_usd": round(n_rows * total_row, 4),
        "tasks": est,
        "first_row_prompt_preview": task_list[0]["user_prompt"][:2000]
    })

@app.route("/api/preview", methods=["POST"])
def preview():
    data = request.get_json(force=True)
    file_id = data.get("file_id")
    if not file_id: return jsonify({"error":"missing file_id"}), 400
    meta = FILES.get(file_id)
    if not meta: return jsonify({"error":"file not found"}), 404

    rows = read_all_rows(meta["path"])
    if not rows: return jsonify({"error":"no rows"}), 400
    first_row = rows[0]
    system_prompt = data.get("system_prompt","")

    tasks = _render_tasks_from_request(data, first_row)
    results = []
    for t in tasks:
        provider = get_provider(t["provider"])
        schema = t["json_schema"] if isinstance(t["json_schema"], dict) else json.loads(t["json_schema"])
        rec, raw, info = provider.generate(
            t["model"], t["user_prompt"], system_prompt, schema,
            max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS","400")),
            enable_web_search=bool(t.get("enable_web_search", False))
        )
        ok, errors = validate_json(rec, schema)
        results.append({
            "task": t["name"], "provider": t["provider"], "model": t["model"],
            "ok": ok, "errors": errors, "raw": raw, "json": rec
        })

    return jsonify({"preview": results})

@app.route("/api/run-all", methods=["POST"])
def run_all():
    data = request.get_json(force=True)
    file_id = data.get("file_id")
    if not file_id: return jsonify({"error":"missing file_id"}), 400
    meta = FILES.get(file_id)
    if not meta: return jsonify({"error":"file not found"}), 404

    rows = read_all_rows(meta["path"])
    n_rows = len(rows)
    if n_rows == 0: return jsonify({"error":"no rows"}), 400

    system_prompt = data.get("system_prompt","")

    tasks_cfg = data.get("tasks")
    single_mode = not (tasks_cfg and isinstance(tasks_cfg, list) and len(tasks_cfg)>0)
    if single_mode:
        tasks_cfg = [{
            "name": data.get("task_name","task1"),
            "provider": data.get("provider","google"),
            "model": data.get("model","gemini-2.5-flash"),
            "enable_web_search": bool(data.get("enable_web_search", False)),
            "json_schema": data.get("json_schema"),
            "prompt_template": data.get("prompt_template","")
        }]

    cache = {}

    def process_row(idx):
        row = rows[idx]
        out = dict(row)
        for t in tasks_cfg:
            key = None
            for k in ["website","url","site","homepage"]:
                if k in row and row[k]:
                    key = f"{t['provider']}::{t['model']}::{normalize_domain(str(row[k]))}"
                    break

            user_prompt = render_prompt_for_row(t.get("prompt_template",""), row)
            schema = t["json_schema"] if isinstance(t["json_schema"], dict) else json.loads(t["json_schema"])
            provider = get_provider(t["provider"])

            if key and key in cache:
                rec, raw, info = cache[key]
            else:
                rec, raw, info = provider.generate(
                    t["model"], user_prompt, system_prompt, schema,
                    max_output_tokens=int(os.getenv("MAX_OUTPUT_TOKENS","400")),
                    enable_web_search=bool(t.get("enable_web_search", False))
                )
                if key: cache[key] = (rec, raw, info)

            ok, errors = validate_json(rec, schema)
            if not ok:
                out[f"ai__{t['name']}__status"] = "schema_failed"
                out[f"ai__{t['name']}__errors"] = "; ".join(errors)
                continue

            flat = flatten_json_record(rec)
            for k, v in flat.items():
                out[f"ai__{t['name']}__{k}"] = v

        out["_row_index"] = idx
        return out

    results = []
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futs = {ex.submit(process_row, i): i for i in range(n_rows)}
        for fut in as_completed(futs):
            results.append(fut.result())

    results.sort(key=lambda r: r.get("_row_index", 0))

    ts = int(time.time())
    out_name = f"result_{file_id}_{ts}.{'xlsx' if data.get('output_format','csv')=='xlsx' else 'csv'}"
    out_path = os.path.join(RESULT_DIR, out_name)

    try:
        import pandas as pd
        df = pd.DataFrame(results)
        if out_name.endswith(".xlsx"):
            df.to_excel(out_path, index=False)
        else:
            df.to_csv(out_path, index=False)
    except Exception as e:
        return jsonify({"error": f"failed to write output: {e}"}), 500

    return jsonify({"ok": True, "file": out_name, "download_url": f"/api/download/{out_name}", "rows_processed": n_rows})

@app.route("/api/download/<path:fname>", methods=["GET"])
def download(fname):
    path = os.path.join(RESULT_DIR, fname)
    if not os.path.exists(path):
        return jsonify({"error":"not found"}), 404
    return send_file(path, as_attachment=True, download_name=fname)

@app.route("/static/<path:fname>", methods=["GET"])
def static_files(fname):
    root = os.path.join(os.path.dirname(__file__), '..', 'frontend')
    return send_from_directory(root, fname)

@app.route("/", methods=["GET"])
def index_html():
    root = os.path.join(os.path.dirname(__file__), '..', 'frontend')
    return send_from_directory(root, 'index.html')

if __name__ == "__main__":
    port = int(os.getenv("PORT","5001"))
    app.run(host="0.0.0.0", port=port, debug=True)
