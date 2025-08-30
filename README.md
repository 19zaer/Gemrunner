# Gem-Runner v2 — Multi-Provider, Multi-Task (CSV/XLSX → LLMs → JSON → CSV/XLSX)

A tiny, clean tool to:
- Upload a CSV/XLSX
- Detect headers + preview first row
- **Choose a model & provider** (Google Gemini, OpenAI GPT, Anthropic Claude, Perplexity Sonar)
- (Optional) **Multi-task mode**: run different prompts/schemas per column group, each with its own model
- Strict **JSON Schema** validation
- **Preview**: run only the **first row**
- **Estimate cost** per row & full sheet (tokens + optional web search/tool fees)
- **Run All** rows (one API call **per task per row**, never per cell)
- Download the completed CSV/XLSX

> **Truthfulness/grounding:** Where supported, you can enable **web search tools** (e.g., Gemini Grounding, OpenAI Web Search, Anthropic Web Search, Perplexity Search). If search is disabled, the model relies on its parametric knowledge only.

---

## What's new in v2 (created 2025-08-30)
- **Providers**: Google Gemini, OpenAI GPT, Anthropic Claude, Perplexity Sonar.
- **Per-task model selection** so e.g. "Country/Description" via Gemini Flash, and "Risk analysis" via Claude Sonnet.
- **Cost estimator** covers model token rates _and_ provider-specific search/tool fees (with adjustable assumptions).
- **Model Catalog**: ships with short descriptions + pricing URL for each provider. **Rates are NOT hardcoded** to avoid staleness — plug in current numbers in `backend/models_catalog.json`.

> Prices & features change frequently. Edit `backend/models_catalog.json` to keep estimates accurate (see linked official pricing pages).

---

## Quickstart

```bash
cd gem-runner-v2
python -m venv .venv
source .venv/bin/activate    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# set one or more API keys (only the providers you plan to use)
export GEMINI_API_KEY="..."
export OPENAI_API_KEY="..."
export ANTHROPIC_API_KEY="..."
export PERPLEXITY_API_KEY="..."

python backend/app.py
# open http://127.0.0.1:5001
```

### Providers & endpoints
- **Gemini**: Google Generative Language API v1beta (structured JSON + Google Search grounding when enabled).
- **OpenAI**: Responses API (json_schema) with Web Search tool (when enabled), falling back to Chat Completions if needed.
- **Anthropic**: Messages API with Structured Outputs + Web Search tool (when enabled).
- **Perplexity**: OpenAI-compatible Chat Completions with search/citations; Deep Research behaves like a search-heavy run.

See `backend/providers/*.py` for exact payloads. If vendors tweak field names, adjust here.

---

## System prompt presets (use these as a starting point)
- **Researcher**: cautious, cites sources, returns `status` = ok/not_found/ambiguous.
- **Analyst**: reasons over the research output (classification, risk flags, scoring).
- **Extractor**: parses pages/snippets and emits normalized fields only.
- **Classifier**: cheap/fast labeler with strict label set & confidence.
- **Summarizer**: concise bullet summary with source attributions.

> You can paste any of these into the "System Prompt" box or customize per task.

---

## Cost estimation
We compute per-row and full-sheet costs by summing across tasks:
```
row_cost = (input_tokens/1e6 * input_rate) + (output_tokens/1e6 * output_rate) + provider_specific_search_component
```
Search/tool fees modeled where applicable (Gemini Grounding, OpenAI/Anthropic Web Search, Perplexity request/search fees).  
**Important:** The repository ships with **0.00** pricing placeholders. Update `backend/models_catalog.json` with current official rates to get accurate estimates.

---

## Security
- Keys are read from env vars on the server. We do not store your keys or data.
- Results & uploads are stored locally under `tmp_*` folders; swap to your storage as needed.

## License
MIT
