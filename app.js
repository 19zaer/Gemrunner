let FILE_ID = null;
let N_ROWS = 0;
let HEADERS = [];
let CATALOG = {};

async function fetchCatalog() {
  const res = await fetch('/api/models');
  const data = await res.json();
  const provToModels = {};
  data.models.forEach(m => {
    if (!provToModels[m.provider]) provToModels[m.provider] = [];
    provToModels[m.provider].push(m);
  });
  CATALOG = provToModels;

  const provSel = document.getElementById('provider');
  provSel.innerHTML = Object.keys(provToModels).map(p => `<option value="${p}">${p}</option>`).join('');
  onProviderChange();

  const catDiv = document.getElementById('catalog');
  let html = '<ul>';
  data.models.forEach(m => {
    const ws = m.web_search ? ` • web: ${JSON.stringify(m.web_search)}` : '';
    const price = (m.input_per_m || m.output_per_m) ? ` — in $${m.input_per_m}/M, out $${m.output_per_m}/M` : ' — pricing not set';
    const link = m.pricing_url ? ` — <a href="${m.pricing_url}" target="_blank">pricing</a>` : '';
    html += `<li><b>${m.display_name}</b> (${m.provider}/${m.model})${price}${ws} — ${m.notes || ''}${link}</li>`;
  });
  html += '</ul>';
  catDiv.innerHTML = html;
}

function onProviderChange() {
  const provider = document.getElementById('provider').value;
  const modelSel = document.getElementById('model');
  const models = (CATALOG[provider] || []);
  modelSel.innerHTML = models.map(m => `<option value="${m.model}">${m.display_name} (${m.model})</option>`).join('');
}

async function upload() {
  const file = document.getElementById('fileInput').files[0];
  if (!file) { alert('Select a file first'); return; }
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/upload', { method: 'POST', body: fd });
  const data = await res.json();
  const out = document.getElementById('uploadResult');
  if (!res.ok) { out.textContent = 'Error: ' + JSON.stringify(data); return; }
  FILE_ID = data.file_id; N_ROWS = data.n_rows; HEADERS = data.headers;
  out.textContent = 'Uploaded. Rows: ' + N_ROWS + '\nFirst row: ' + JSON.stringify(data.sample_first_row, null, 2);
  document.getElementById('configSection').style.display = 'block';
  document.getElementById('headersList').textContent = HEADERS.join(', ');
  const schemaRes = await fetch('/static/schema.json');
  document.getElementById('jsonSchema').value = await schemaRes.text();
  fetchCatalog();
}

function buildTasksForRequest(singleOnly=false) {
  const sys = document.getElementById('systemPrompt').value.trim();
  const basicProvider = document.getElementById('provider').value;
  const basicModel = document.getElementById('model').value;
  const enableSearch = document.getElementById('enableSearch').checked;
  const searchCalls = parseFloat(document.getElementById('searchCalls').value || '0');
  const maxOut = parseInt(document.getElementById('maxOut').value || '400');
  const pt = document.getElementById('promptTemplate').value.trim();
  const js = document.getElementById('jsonSchema').value.trim();
  const tasksJson = document.getElementById('tasksJson').value.trim();

  const base = { file_id: FILE_ID, system_prompt: sys, max_output_tokens: maxOut, est_search_calls_per_row: searchCalls };

  if (singleOnly || !tasksJson) {
    return {
      ...base,
      provider: basicProvider,
      model: basicModel,
      prompt_template: pt,
      json_schema: js,
      enable_web_search: enableSearch
    };
  }

  let tasks = [];
  try { tasks = JSON.parse(tasksJson); } catch (e) { alert('Tasks JSON invalid'); return null; }
  return { ...base, tasks };
}

async function estimate() {
  const body = buildTasksForRequest(false) || buildTasksForRequest(true);
  if (!body) return;
  const res = await fetch('/api/estimate', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const data = await res.json();
  document.getElementById('estimateOut').textContent = JSON.stringify(data, null, 2);
  if (res.ok) document.getElementById('previewSection').style.display = 'block';
}

async function preview() {
  const body = buildTasksForRequest(false) || buildTasksForRequest(true);
  if (!body) return;
  const res = await fetch('/api/preview', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const data = await res.json();
  document.getElementById('previewOut').textContent = JSON.stringify(data, null, 2);
  if (res.ok) document.getElementById('runAllSection').style.display = 'block';
}

async function runAll() {
  const outFormat = document.getElementById('outFormat').value;
  const body = buildTasksForRequest(false) || buildTasksForRequest(true);
  if (!body) return;
  body['output_format'] = outFormat;
  const res = await fetch('/api/run-all', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(body) });
  const data = await res.json();
  if (!res.ok) { document.getElementById('runAllOut').textContent = 'Error: ' + JSON.stringify(data, null, 2); return; }
  const link = location.origin + data.download_url;
  document.getElementById('runAllOut').innerHTML = JSON.stringify(data, null, 2) + "\n\nDownload: " + link;
}

document.getElementById('uploadBtn').addEventListener('click', upload);
document.getElementById('estimateBtn').addEventListener('click', estimate);
document.getElementById('previewBtn').addEventListener('click', preview);
document.getElementById('runAllBtn').addEventListener('click', runAll);
document.getElementById('provider').addEventListener('change', onProviderChange);
