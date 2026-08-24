/* 评测工作台：配置与结果两个二级页面。 */
(() => {
  const state = window.__evWorkspace = window.__evWorkspace || { tab: "config", compositionId: null, runId: null, results: [], threshold: .5 };
  const $w = () => document.getElementById("evWorkspace");
  const post = async (path, body) => {
    const r = await fetch(API_BASE + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.status); }
    return r.json();
  };
  const esc = v => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));

  function shell(content) {
    $w().innerHTML = `<div class="ev-layout"><aside class="ev-side"><button class="ev-side-item ${state.tab === "config" ? "on" : ""}" data-ev-tab="config"><i data-lucide="sliders-horizontal"></i><span>评测配置</span></button><button class="ev-side-item ${state.tab === "results" ? "on" : ""}" data-ev-tab="results"><i data-lucide="chart-no-axes-combined"></i><span>评测结果</span></button></aside><div class="ev-main">${content}</div></div>`;
    icons();
  }

  async function config() {
    const compositions = await apiGet("/api/compositions").catch(() => []);
    if (window.__evSelectedCompositionId) { state.compositionId = Number(window.__evSelectedCompositionId); window.__evSelectedCompositionId = null; }
    shell(`<div class="card card-pad"><div class="card-t">请求体设置</div><div class="ev-call-types" id="evCallTypes"><button class="on" data-adapter="openai_compatible">OpenAI 兼容接口</button><button data-adapter="http">通用 HTTP</button><button data-adapter="mock">Mock 演示</button></div>
      <div id="evAdapterFields"></div></div>
      <div class="card card-pad ev-section"><div class="card-t">选择评测集</div><p class="es-gen-hint">仅可选择评测库中的正式评测集版本。单个来源也需先创建为评测库版本，以便追踪与复用。</p><div class="ev-set-actions"><button class="btn ghost" id="evCreateSet"><i data-lucide="combine"></i>创建 / 合并评测集</button></div><div class="ev-compositions">${compositions.length ? compositions.map(c => `<label class="ev-composition ${Number(c.composition_id) === state.compositionId ? "selected" : ""}"><input type="radio" name="evComposition" value="${c.composition_id}" ${Number(c.composition_id) === state.compositionId ? "checked" : ""}/><span><b>${esc(c.name)}</b><small>版本 #${c.composition_id} · ${Array.isArray(c.items) ? c.items.length : 0} 个来源</small></span></label>`).join("") : `<div class="es-gen-hint">暂无评测库版本，请先创建或合并评测集。</div>`}</div></div>
      <div class="ev-run-foot"><label class="es-field">运行名称（可选）</label><input class="es-input" id="evRunName" placeholder="例如：客服智能体 v0.1 回归测试"/><button class="btn primary" id="evStart"><i data-lucide="play"></i>发起评测</button></div>`);
    // Demo 不提供 Mock 入口；评测集以可展开的“评测库”目录展示。
    document.querySelector('[data-adapter="mock"]').remove();
    const compositionBox = document.querySelector(".ev-compositions");
    const folder = document.createElement("button");
    folder.type = "button"; folder.className = "ev-library-folder";
    folder.innerHTML = `<i data-lucide="chevron-down"></i><i data-lucide="folder-open"></i><b>评测库</b><span>${compositions.length}</span>`;
    compositionBox.parentNode.insertBefore(folder, compositionBox);
    folder.onclick = () => { const closed = compositionBox.classList.toggle("collapsed"); folder.querySelector("svg").setAttribute("data-lucide", closed ? "chevron-right" : "chevron-down"); icons(); };
    const nameInput = document.getElementById("evRunName");
    nameInput.previousElementSibling.remove(); nameInput.remove();
    setAdapter("openai_compatible");
    document.querySelectorAll("#evCallTypes button").forEach(b => b.onclick = () => setAdapter(b.dataset.adapter));
    document.querySelectorAll("input[name=evComposition]").forEach(i => i.onchange = () => { state.compositionId = Number(i.value); document.querySelectorAll(".ev-composition").forEach(x => x.classList.toggle("selected", x.querySelector("input").checked)); });
    document.getElementById("evCreateSet").onclick = () => { window.__evalSetReturn = "evaluation"; goto("evalset"); };
    document.getElementById("evStart").onclick = start;
    icons();
  }

  function setAdapter(kind) {
    state.adapter = kind;
    document.querySelectorAll("#evCallTypes button").forEach(b => b.classList.toggle("on", b.dataset.adapter === kind));
    const fields = document.getElementById("evAdapterFields");
    if (kind === "openai_compatible") fields.innerHTML = `<div class="ev-field-grid"><label class="es-field">API Base<input class="es-input" id="evApiBase" placeholder="https://.../v1"/></label><label class="es-field">模型<input class="es-input" id="evModel" placeholder="gpt-4o-mini"/></label><label class="es-field">API Key<input class="es-input" id="evApiKey" type="password" placeholder="sk-..."/></label><label class="es-field">System Prompt<textarea class="es-input" id="evSystem" rows="2" placeholder="可选"></textarea></label></div>`;
    else fields.innerHTML = `<div class="ev-field-grid"><label class="es-field">请求方法<select class="es-input" id="evHttpMethod"><option>POST</option><option>GET</option><option>PUT</option><option>PATCH</option><option>DELETE</option></select></label><label class="es-field">请求地址<input class="es-input" id="evHttpUrl" placeholder="https://agent.example.com/api/chat"/></label><label class="es-field ev-span">请求头（JSON）<textarea class="es-input ev-code" id="evHttpHeaders" rows="2" placeholder='{"Authorization":"Bearer ..."}'></textarea></label><label class="es-field ev-span">请求体（JSON，使用 {{question}} 注入题目）<textarea class="es-input ev-code" id="evHttpBody" rows="4">{"question":"{{question}}"}</textarea></label><label class="es-field">回答字段路径<input class="es-input" id="evHttpPath" value="answer" placeholder="data.answer"/></label><label class="es-field">超时（秒）<input class="es-input" id="evHttpTimeout" type="number" value="60" min="1" max="120"/></label></div><p class="es-gen-hint">请求由后端发起；Header 的值不会保存或在报告中回显。</p>`;
  }

  function adapterConfig() {
    if (state.adapter === "openai_compatible") return { api_base: document.getElementById("evApiBase").value.trim(), api_key: document.getElementById("evApiKey").value.trim(), model: document.getElementById("evModel").value.trim(), system_prompt: document.getElementById("evSystem").value.trim() || null };
    let headers; try { headers = JSON.parse(document.getElementById("evHttpHeaders").value || "{}"); } catch { throw new Error("请求头必须是合法 JSON"); }
    try { JSON.parse(document.getElementById("evHttpBody").value || "{}"); } catch { throw new Error("请求体必须是合法 JSON"); }
    return { method: document.getElementById("evHttpMethod").value, url: document.getElementById("evHttpUrl").value.trim(), headers, body_template: document.getElementById("evHttpBody").value, answer_path: document.getElementById("evHttpPath").value.trim(), timeout_seconds: Number(document.getElementById("evHttpTimeout").value) };
  }

  async function start() {
    if (!state.compositionId) return toast("请先从评测库选择一个评测集");
    try {
      const run = await post("/api/evaluation-runs", { composition_id: state.compositionId, name: null, adapter: state.adapter, adapter_config: adapterConfig() });
      state.runId = run.run_id; state.tab = "results"; render(); toast("已发起评测运行");
    } catch (e) { toast("发起失败：" + e.message); }
  }

  function metrics(summary, rows) {
    const total = summary.total || rows.length, passed = summary.passed || 0, error = summary.error_count || 0;
    const avg = rows.length ? Math.round(rows.reduce((n, x) => n + Number((x.scores || {}).latency_ms || 0), 0) / rows.length) : 0;
    return `<div class="ev-kpis"><div><span class="ev-kpi-ic"><i data-lucide="list-checks"></i></span><small>总题数</small><b>${total}</b></div><div><span class="ev-kpi-ic"><i data-lucide="badge-check"></i></span><small>通过率</small><b>${total ? Math.round(passed / total * 100) : 0}%</b></div><div><span class="ev-kpi-ic"><i data-lucide="timer"></i></span><small>平均用时</small><b>${avg} ms</b></div><div><span class="ev-kpi-ic"><i data-lucide="circle-alert"></i></span><small>异常数</small><b>${error}</b></div></div>`;
  }

  async function results() {
    const runs = await apiGet("/api/evaluation-runs").catch(() => []);
    if (!state.runId && runs[0]) state.runId = runs[0].run_id;
    let data = { results: [], summary: {} }, run = null;
    if (state.runId) { data = await apiGet(`/api/evaluation-runs/${state.runId}/results`).catch(() => data); run = runs.find(x => x.run_id === state.runId); }
    state.results = data.results || [];
    shell(`<div class="ev-result-head"><div><label class="es-field">评测运行</label><select class="es-input" id="evRunSelect"><option value="">请选择运行</option>${runs.map(r => `<option value="${r.run_id}" ${r.run_id === state.runId ? "selected" : ""}>#${r.run_id} ${esc(r.name || "未命名运行")} · ${esc(r.status)}</option>`).join("")}</select></div><div class="ev-threshold"><label class="es-field">通过阈值</label><input class="es-input" id="evThreshold" type="number" min="0" max="1" step=".05" value="${state.threshold}"/></div></div>${run && run.status === "running" ? `<div class="ev-progress"><div class="ev-bar"><span style="width:${run.progress || 0}%"></span></div><div class="ev-progress-t">跑批中 ${run.finished || 0}/${run.total || 0}</div></div>` : ""}${metrics(data.summary || {}, state.results)}<div class="card card-pad ev-report"><div class="card-t">原始评测报告</div><div class="ev-filters"><input class="es-input" id="evSearch" placeholder="搜索问题、标准答案或智能体回答"/><select class="es-input" id="evStatus"><option value="">全部状态</option><option value="passed">通过</option><option value="failed">未通过</option><option value="error">异常</option><option value="diagnosis">有 ErrorBook</option></select><button class="btn ghost" id="evLow">仅低于阈值</button></div><div class="ev-table-wrap"><table class="ev-table"><thead><tr><th>问题 / 标准答案</th><th>智能体回答 A'</th><th>得分</th><th>耗时</th><th>状态 / 归因</th></tr></thead><tbody id="evReportRows"></tbody></table></div></div>`);
    document.getElementById("evRunSelect").onchange = e => { state.runId = Number(e.target.value) || null; render(); };
    ["evSearch", "evStatus", "evThreshold"].forEach(id => document.getElementById(id).oninput = filterRows);
    document.getElementById("evLow").onclick = e => { e.currentTarget.classList.toggle("on"); filterRows(); };
    filterRows(); icons();
    if (run && run.status === "running") setTimeout(() => { if (state.tab === "results") render(); }, 2000);
  }

  function filterRows() {
    const q = document.getElementById("evSearch").value.toLowerCase(), status = document.getElementById("evStatus").value;
    state.threshold = Number(document.getElementById("evThreshold").value || .5);
    const low = document.getElementById("evLow").classList.contains("on");
    const rows = state.results.filter(r => { const score = (r.scores || {}).score; const hay = `${r.question} ${r.gold_answer} ${r.answer}`.toLowerCase(); return (!q || hay.includes(q)) && (!status || (status === "diagnosis" ? r.diagnosis : r.status === status)) && (!low || (score != null && score < state.threshold)); });
    document.getElementById("evReportRows").innerHTML = rows.length ? rows.map(r => { const s = r.scores || {}, diag = r.diagnosis || {}; return `<tr><td><b>${esc(r.question)}</b><small>标准答案：${esc(r.gold_answer || "—")}</small></td><td>${esc(r.answer || r.error_message || "—")}</td><td>${s.score == null ? "—" : Math.round(s.score * 100) + ""}</td><td>${s.latency_ms == null ? "—" : s.latency_ms + " ms"}</td><td><span class="es-tag ${r.status === "passed" ? "ok" : r.status === "error" ? "bad" : "warn"}">${esc(r.status || "—")}</span>${diag.root_cause ? `<small class="ev-errorbook">${esc(diag.root_cause)}</small>` : ""}</td></tr>`; }).join("") : `<tr><td colspan="5" class="es-gen-hint">没有符合条件的结果。</td></tr>`;
  }

  async function render() { if (!$w()) return; if (state.tab === "config") await config(); else await results(); }
  window.renderEvaluation = render;
  document.addEventListener("click", e => { const tab = e.target.closest("[data-ev-tab]"); if (tab) { state.tab = tab.dataset.evTab; render(); } if (e.target.closest("#evConfigBtn")) { state.tab = "config"; render(); } });
})();
