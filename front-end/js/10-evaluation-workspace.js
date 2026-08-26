/* 评测工作台：配置与结果两个二级页面。 */
(() => {
  const state = window.__evWorkspace = window.__evWorkspace || {
    tab: "config",
    compositionId: null,
    runId: null,
    results: [],
    filteredResults: [],
    threshold: .5,
    runs: [],
  };
  const $w = () => document.getElementById("evWorkspace");
  const post = async (path, body) => {
    const r = await fetch(API_BASE + path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.status); }
    return r.json();
  };
  const esc = v => String(v == null ? "" : v).replace(/[&<>"']/g, c => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#39;" }[c]));
  const parseServerDate = value => {
    if (value instanceof Date) return value;
    const text = String(value || "");
    return new Date(text && !/[zZ]|[+-]\d{2}:?\d{2}$/.test(text) ? `${text}Z` : text);
  };
  const formatDateTime = value => {
    const date = parseServerDate(value);
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric", month: "2-digit", day: "2-digit",
      hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false,
    }).format(date).replaceAll("/", "-");
  };
  const defaultRunName = compositionName => `${compositionName}_${formatDateTime(new Date()).replace(/[\s:]/g, "-")}`;
  const formatDuration = seconds => {
    if (!Number.isFinite(seconds) || seconds < 0) return "计算中";
    const rounded = Math.max(0, Math.round(seconds));
    if (rounded < 60) return `约 ${rounded} 秒`;
    const minutes = Math.floor(rounded / 60), remain = rounded % 60;
    if (minutes < 60) return `约 ${minutes} 分 ${remain} 秒`;
    const hours = Math.floor(minutes / 60), remainMinutes = minutes % 60;
    return `约 ${hours} 小时 ${remainMinutes} 分`;
  };
  const estimateRemaining = run => {
    const finished = Number(run.finished || 0), total = Number(run.total || 0);
    if (!run.started_at || finished < 1 || total <= finished) return total && total <= finished ? "即将完成" : "计算中";
    const elapsedSeconds = Math.max(0, (Date.now() - parseServerDate(run.started_at).getTime()) / 1000);
    return formatDuration(elapsedSeconds / finished * (total - finished));
  };
  const maskHeaders = headers => Object.fromEntries(Object.keys(headers || {}).map(key => [key, "••••••"]));
  const patch = async (path, body) => {
    const r = await fetch(API_BASE + path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.status); }
    return r.json();
  };
  const PROFILE_KEY = "evalforge-agent-profiles-v1";
  const loadProfiles = () => { try { return JSON.parse(localStorage.getItem(PROFILE_KEY) || "[]"); } catch { return []; } };
  const storeProfiles = profiles => localStorage.setItem(PROFILE_KEY, JSON.stringify(profiles));
  const publicProfileConfig = (kind, config) => {
    const safe = { ...config };
    delete safe.api_key;
    if (kind === "http" && safe.headers) safe.headers = Object.fromEntries(Object.keys(safe.headers).map(key => [key, ""]));
    return safe;
  };
  const runStatusLabel = status => ({ pending: "等待中", running: "运行中", cancelling: "取消中", cancelled: "已取消", done: "已完成", failed: "失败" })[status] || status || "未知";
  const caseStatusLabel = status => ({ passed: "通过", failed: "未通过", error: "异常", unscored: "未评分", pending: "等待中" })[status] || status || "—";

  function shell(content, sideExtra) {
    $w().innerHTML = `<div class="ev-layout"><aside class="ev-side"><button class="ev-side-item ${state.tab === "config" ? "on" : ""}" data-ev-tab="config"><i data-lucide="sliders-horizontal"></i><span>评测配置</span></button><button class="ev-side-item ${state.tab === "results" ? "on" : ""}" data-ev-tab="results"><i data-lucide="chart-no-axes-combined"></i><span>评测结果</span></button>${sideExtra || ""}</aside><div class="ev-main">${content}</div></div>`;
    icons();
  }

  async function config() {
    const compositions = await apiGet("/api/compositions");
    if (window.__evSelectedCompositionId) { state.compositionId = Number(window.__evSelectedCompositionId); window.__evSelectedCompositionId = null; }
    const profiles = loadProfiles();
    shell(`<div class="card card-pad"><div class="ev-config-head"><div><div class="card-t">请求体设置</div><p>配置可保存为浏览器内的复用模板，密钥和 Header 值不会保存。</p></div><div class="ev-profile-actions"><select class="es-input" id="evProfile"><option value="">选择已保存配置</option>${profiles.map(item => `<option value="${esc(item.id)}">${esc(item.name)}</option>`).join("")}</select><button class="btn ghost" id="evSaveProfile"><i data-lucide="save"></i>保存配置</button><button class="btn ghost" id="evTestAdapter"><i data-lucide="plug-zap"></i>测试通路</button></div></div><div class="ev-call-types" id="evCallTypes"><button class="on" data-adapter="openai_compatible">OpenAI 兼容接口</button><button data-adapter="http">通用 HTTP</button><button data-adapter="mock">Mock 演示</button></div>
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
    document.getElementById("evProfile").onchange = event => {
      const profile = loadProfiles().find(item => item.id === event.target.value);
      if (!profile) return;
      setAdapter(profile.adapter);
      applyAdapterConfig(profile.adapter, profile.config || {});
    };
    document.getElementById("evSaveProfile").onclick = saveCurrentProfile;
    document.getElementById("evTestAdapter").onclick = testCurrentAdapter;
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

  function applyAdapterConfig(kind, config) {
    if (kind === "openai_compatible") {
      document.getElementById("evApiBase").value = config.api_base || "";
      document.getElementById("evModel").value = config.model || "";
      document.getElementById("evSystem").value = config.system_prompt || "";
    } else {
      document.getElementById("evHttpMethod").value = config.method || "POST";
      document.getElementById("evHttpUrl").value = config.url || "";
      document.getElementById("evHttpHeaders").value = JSON.stringify(config.headers || {}, null, 2);
      document.getElementById("evHttpBody").value = config.body_template || '{"question":"{{question}}"}';
      document.getElementById("evHttpPath").value = config.answer_path || "answer";
      document.getElementById("evHttpTimeout").value = config.timeout_seconds || 60;
    }
  }

  function saveCurrentProfile() {
    let cfg;
    try { cfg = adapterConfig(); } catch (error) { return toast(error.message); }
    const name = prompt("配置名称", state.adapter === "http" ? "通用 HTTP 智能体" : "OpenAI 兼容智能体");
    if (!name || !name.trim()) return;
    const profiles = loadProfiles();
    profiles.push({ id: `${Date.now()}`, name: name.trim(), adapter: state.adapter, config: publicProfileConfig(state.adapter, cfg) });
    storeProfiles(profiles);
    toast("配置已保存；使用时仍需填写密钥或请求头敏感值");
    config();
  }

  async function testCurrentAdapter() {
    const question = prompt("输入一条用于测试通路的问题", "请简要介绍你的能力");
    if (!question || !question.trim()) return;
    const button = document.getElementById("evTestAdapter");
    button.disabled = true; button.innerHTML = '<span class="spinner"></span>测试中';
    try {
      const data = await post("/api/adapters/test", { adapter: state.adapter, adapter_config: adapterConfig(), question: question.trim() });
      openMessageModal("通路测试成功", data.answer || "目标智能体返回了空回答", `耗时 ${Number(data.usage?.time_ms || 0)} ms`);
    } catch (error) { toast("通路测试失败：" + error.message); }
    finally { button.disabled = false; button.innerHTML = '<i data-lucide="plug-zap"></i>测试通路'; icons(); }
  }

  function openMessageModal(title, message, meta = "") {
    const modal = document.createElement("div"); modal.className = "modal-mask";
    modal.innerHTML = `<div class="modal ev-message-modal"><div class="modal-head"><span>${esc(title)}</span><button class="modal-x">×</button></div><div class="modal-body"><p class="ev-message-body">${esc(message)}</p>${meta ? `<small>${esc(meta)}</small>` : ""}</div><div class="modal-foot"><button class="btn primary modal-x2">知道了</button></div></div>`;
    document.body.appendChild(modal); const close = () => modal.remove(); modal.querySelector(".modal-x").onclick = close; modal.querySelector(".modal-x2").onclick = close;
  }

  async function start() {
    if (!state.compositionId) return toast("请先从评测库选择一个评测集");
    try {
      const compositions = await apiGet("/api/compositions");
      const composition = compositions.find(item => Number(item.composition_id) === Number(state.compositionId));
      if (!composition) return toast("所选评测集版本不存在，请重新选择");
      openRunConfirmation(composition, adapterConfig());
    } catch (e) { toast("发起失败：" + e.message); }
  }

  function openRunConfirmation(composition, config) {
    const modal = document.createElement("div");
    modal.className = "modal-mask";
    const adapterLabel = state.adapter === "http" ? "通用 HTTP" : "OpenAI 兼容接口";
    const requestSummary = state.adapter === "http" ? {
      method: config.method,
      url: config.url,
      headers: maskHeaders(config.headers),
      body: (() => { try { return JSON.parse(config.body_template || "{}"); } catch { return config.body_template; } })(),
      answer_path: config.answer_path,
      timeout_seconds: config.timeout_seconds,
    } : {
      api_base: config.api_base,
      model: config.model,
      api_key: config.api_key ? "••••••" : "未填写",
      system_prompt: config.system_prompt || "未设置",
      request_body: {
        model: config.model || "<model>",
        messages: [
          ...(config.system_prompt ? [{ role: "system", content: config.system_prompt }] : []),
          { role: "user", content: "{{question}}" },
        ],
      },
    };
    modal.innerHTML = `<div class="modal ev-confirm-modal">
      <div class="modal-head"><span>确认发起评测</span><button class="modal-x" aria-label="关闭">×</button></div>
      <div class="modal-body">
        <label class="es-field" for="evConfirmName">运行名称</label>
        <input class="es-input" id="evConfirmName" maxlength="255" value="${esc(defaultRunName(composition.name || `评测集-${composition.composition_id}`))}" />
        <div class="ev-confirm-grid">
          <section class="ev-confirm-card"><div class="ev-confirm-label">请求配置</div><b>${esc(adapterLabel)}</b><pre>${esc(JSON.stringify(requestSummary, null, 2))}</pre></section>
          <section class="ev-confirm-card"><div class="ev-confirm-label">可执行评测集</div><b>${esc(composition.name || `评测集 #${composition.composition_id}`)}</b><dl><div><dt>版本</dt><dd>#${composition.composition_id}</dd></div><div><dt>来源数</dt><dd>${Array.isArray(composition.items) ? composition.items.length : 0}</dd></div><div><dt>创建时间</dt><dd>${esc(formatDateTime(composition.created_at))}</dd></div></dl></section>
        </div>
        <p class="ev-confirm-note"><i data-lucide="shield-check"></i>密钥及请求头敏感值仅以掩码展示，不会写入评测报告。</p>
      </div>
      <div class="modal-foot"><button class="btn ghost modal-cancel">返回修改</button><button class="btn primary" id="evConfirmStart"><i data-lucide="play"></i>确认发起</button></div>
    </div>`;
    document.body.appendChild(modal);
    icons();
    const close = () => modal.remove();
    modal.querySelector(".modal-x").onclick = close;
    modal.querySelector(".modal-cancel").onclick = close;
    modal.addEventListener("click", event => { if (event.target === modal) close(); });
    modal.querySelector("#evConfirmStart").onclick = async event => {
      const name = modal.querySelector("#evConfirmName").value.trim();
      if (!name) return toast("请填写运行名称");
      const button = event.currentTarget;
      button.disabled = true;
      button.innerHTML = '<span class="spinner"></span>正在发起';
      try {
        const run = await post("/api/evaluation-runs", { composition_id: state.compositionId, name, adapter: state.adapter, adapter_config: config });
        state.runId = run.run_id;
        state.tab = "results";
        close();
        render();
        toast("评测已发起，正在执行跑批");
      } catch (error) {
        button.disabled = false;
        button.innerHTML = '<i data-lucide="play"></i>确认发起';
        icons();
        toast("发起失败：" + error.message);
      }
    };
    modal.querySelector("#evConfirmName").focus();
    modal.querySelector("#evConfirmName").select();
  }

  function analysisStats(rows, threshold = state.threshold) {
    const scored = rows.filter(item => Number.isFinite(Number(item.scores?.score)) && item.scores?.score != null);
    const passed = scored.filter(item => Number(item.scores.score) >= threshold);
    const errors = rows.filter(item => item.status === "error");
    const latencies = rows.map(item => Number(item.scores?.latency_ms)).filter(Number.isFinite).sort((a, b) => a - b);
    const averageScore = scored.length ? scored.reduce((sum, item) => sum + Number(item.scores.score), 0) / scored.length : null;
    const p95 = latencies.length ? latencies[Math.min(latencies.length - 1, Math.ceil(latencies.length * .95) - 1)] : null;
    return { total: rows.length, scored: scored.length, passed: passed.length, low: scored.length - passed.length, errors: errors.length, averageScore, p95 };
  }

  function metrics(rows) {
    const stat = analysisStats(rows);
    return `<div id="evAnalysisMetrics" class="ev-kpis"><div><span class="ev-kpi-ic"><i data-lucide="badge-check"></i></span><small>分析通过率</small><b>${stat.scored ? Math.round(stat.passed / stat.scored * 100) : 0}%</b><em>${stat.passed}/${stat.scored} 道已评分题</em></div><div><span class="ev-kpi-ic"><i data-lucide="chart-spline"></i></span><small>平均得分</small><b>${stat.averageScore == null ? "—" : Math.round(stat.averageScore * 100)}</b><em>按当前分析阈值 ${state.threshold.toFixed(2)}</em></div><div><span class="ev-kpi-ic"><i data-lucide="circle-alert"></i></span><small>调用异常</small><b>${stat.errors}</b><em>${stat.low} 道答案未通过</em></div><div><span class="ev-kpi-ic"><i data-lucide="timer"></i></span><small>P95 耗时</small><b>${stat.p95 == null ? "—" : Math.round(stat.p95) + " ms"}</b><em>${stat.total} 道原始结果</em></div></div>`;
  }

  function refreshAnalysisMetrics() {
    const target = document.getElementById("evAnalysisMetrics");
    if (!target) return;
    const holder = document.createElement("div"); holder.innerHTML = metrics(state.results);
    target.replaceWith(holder.firstElementChild); icons();
  }

  async function results() {
    const [runs, compositions] = await Promise.all([
      apiGet("/api/evaluation-runs"),
      apiGet("/api/compositions"),
    ]);
    state.runs = runs;
    if (!state.runId && runs[0]) state.runId = runs[0].run_id;
    let data = { results: [], summary: {} }, run = null;
    if (state.runId) { data = await apiGet(`/api/evaluation-runs/${state.runId}/results`); run = runs.find(x => x.run_id === state.runId); }
    state.results = data.results || [];
    const groups = compositions.map(composition => ({
      ...composition,
      runs: runs.filter(item => Number(item.composition_id) === Number(composition.composition_id)),
    })).filter(group => group.runs.length);
    const orphanRuns = runs.filter(item => !compositions.some(composition => Number(composition.composition_id) === Number(item.composition_id)));
    if (orphanRuns.length) groups.push({ composition_id: "unknown", name: "历史评测集", runs: orphanRuns });
    const selectedComposition = run ? compositions.find(item => Number(item.composition_id) === Number(run.composition_id)) : null;
    const catalog = runs.length ? `<div class="es-library-tree ev-side-catalog">${groups.map(group => {
      const selected = run && String(group.composition_id) === String(run.composition_id);
      const runNode = item => {
        const icon = item.status === "done" ? "circle-check" : item.status === "failed" ? "circle-x" : item.status === "cancelled" ? "circle-stop" : ["running", "cancelling"].includes(item.status) ? "loader" : "clock";
        const badge = item.status === "done" && item.pass_rate != null
          ? `<span class="tw-count" style="color:#2f7d5b;background:rgba(47,125,91,.12)">${Math.round(item.pass_rate * 100)}%</span>`
          : item.status === "failed" ? `<span class="tw-count" style="color:#c0392b;background:rgba(192,57,43,.12)">失败</span>`
          : `<span class="tw-count">${esc(runStatusLabel(item.status))}</span>`;
        return `<div class="tree-row ${item.run_id === state.runId ? "active" : ""}" data-run-id="${item.run_id}"><i data-lucide="${icon}" class="tw-ic"></i><span class="tw-name">${esc(item.name || `运行 #${item.run_id}`)}</span>${badge}<button class="tree-dots" data-run-dots="${item.run_id}" title="更多操作"><i data-lucide="more-horizontal"></i></button></div>`;
      };
      return `<div class="tree-node">
        <div class="tree-row tree-folder" data-ev-group="${esc(String(group.composition_id))}"><i data-lucide="folder" class="tw-ic"></i><span class="tw-name">${esc(group.name || `评测集 #${group.composition_id}`)}</span><span class="tw-count">${group.runs.length}</span><i data-lucide="${selected ? "chevron-down" : "chevron-right"}" class="tw-chev"></i></div>
        <div class="tree-children ${selected ? "open" : ""}">${group.runs.map(runNode).join("")}</div>
      </div>`;
    }).join("")}</div>` : `<div class="es-library-tree ev-side-catalog"><div class="ev-empty-catalog"><i data-lucide="folder-search"></i><span>暂无评测结果</span></div></div>`;
    const progress = run && ["running", "cancelling"].includes(run.status) ? `<section class="ev-progress-card"><div class="ev-progress-head"><div><span class="ev-running-dot"></span><b>${run.status === "cancelling" ? "正在取消" : "评测执行中"}</b><small>${run.status === "cancelling" ? "当前单题请求结束后停止" : "完成后将自动刷新指标与原始报告"}</small></div><div class="ev-progress-actions"><strong>${Number(run.progress || 0)}%</strong>${run.status === "running" ? '<button class="btn ghost" id="evCancelRun"><i data-lucide="square"></i>取消运行</button>' : ""}</div></div><div class="ev-bar"><span style="width:${Number(run.progress || 0)}%"></span></div><div class="ev-progress-meta"><span>${Number(run.finished || 0)} / ${Number(run.total || 0)} 题</span><span><i data-lucide="clock-3"></i>预计剩余 ${esc(estimateRemaining(run))}</span></div></section>` : "";
    const content = run ? `<div class="ev-result-title"><div><span class="es-tag">${esc(runStatusLabel(run.status))}</span><h2>${esc(run.name || `运行 #${run.run_id}`)}</h2><p>${esc(selectedComposition?.name || `评测集 #${run.composition_id}`)} · 版本 #${esc(run.composition_id)} · ${esc(formatDateTime(run.created_at))}</p></div><div class="ev-result-actions"><button class="btn ghost" id="evCompareRun"><i data-lucide="git-compare-arrows"></i>版本对比</button><label class="ev-threshold">分析阈值<input class="es-input" id="evThreshold" type="number" min="0" max="1" step=".05" value="${state.threshold}"/><small>仅影响当前页面分析</small></label></div></div>${progress}${metrics(state.results)}<div class="card card-pad ev-report"><div class="ev-report-head"><div><div class="card-t">原始评测报告</div><p>原始结果不会因人工处置消失；点击任意行查看评分明细、处理记录和单题复测。</p></div><div class="ev-export-wrap"><button class="btn ghost" id="evExportToggle"><i data-lucide="download"></i>导出报告<i data-lucide="chevron-down"></i></button><div class="ev-export-popover" id="evExportPopover" hidden><label><input type="checkbox" id="evExportFiltered"/>仅导出当前筛选结果</label><small>默认导出当前运行的全部原始报告</small><button class="btn primary" id="evExportConfirm"><i data-lucide="file-spreadsheet"></i>导出 Excel</button></div></div></div><div class="ev-filters"><input class="es-input" id="evSearch" placeholder="搜索问题、标准答案或智能体回答"/><select class="es-input" id="evStatus"><option value="">全部结果</option><option value="meets">达到分析阈值</option><option value="below">答案未通过</option><option value="error">调用异常</option><option value="unscored">未评分</option><option value="open">待处理</option><option value="processed">已处理待复测</option><option value="verified">已验证</option><option value="ignored">已忽略</option></select></div><div class="ev-table-wrap"><table class="ev-table"><thead><tr><th>问题 / 标准答案</th><th>智能体回答 A'</th><th>得分</th><th>耗时</th><th>结果 / 处理状态</th></tr></thead><tbody id="evReportRows"></tbody></table></div></div>` : `<div class="ev-result-empty"><span><i data-lucide="chart-no-axes-combined"></i></span><h2>选择一次评测运行</h2><p>从左侧「评测结果目录」中展开并选择运行，即可查看指标和原始报告。</p><button class="btn primary" id="evConfigBtn">前往评测配置</button></div>`;
    shell(`<div class="ev-results-layout ev-results-single"><div class="ev-result-content">${content}</div></div>`, catalog);
    // 仿评测集库目录交互（事件委托到稳定的父容器，子节点重建也不丢监听）
    const catalogEl = $w().querySelector(".ev-side-catalog");
    if (catalogEl) {
      catalogEl.onclick = (e) => {
        const dot = e.target.closest(".tree-dots[data-run-dots]");
        if (dot) {
          e.stopPropagation();
          openRunMenu(runs.find(item => Number(item.run_id) === Number(dot.dataset.runDots)), dot);
          return;
        }
        const folder = e.target.closest(".tree-row.tree-folder");
        if (folder) {
          const kids = folder.closest(".tree-node").querySelector(".tree-children");
          if (kids) kids.classList.toggle("open");
          const chev = folder.querySelector(".tw-chev");
          if (chev) chev.setAttribute("data-lucide", kids.classList.contains("open") ? "chevron-down" : "chevron-right");
          icons();
          return;
        }
        const row = e.target.closest(".tree-row[data-run-id]");
        if (row) { state.runId = Number(row.dataset.runId); render(); }
      };
    }
    if (!run) { icons(); return; }
    ["evSearch", "evStatus", "evThreshold"].forEach(id => document.getElementById(id).oninput = filterRows);
    const exportToggle = document.getElementById("evExportToggle"), exportPopover = document.getElementById("evExportPopover");
    exportToggle.onclick = event => { event.stopPropagation(); exportPopover.hidden = !exportPopover.hidden; };
    exportPopover.onclick = event => event.stopPropagation();
    document.getElementById("evExportConfirm").onclick = exportReport;
    document.getElementById("evCompareRun").onclick = () => openRunComparison(run, runs);
    if (document.getElementById("evCancelRun")) document.getElementById("evCancelRun").onclick = () => cancelRun(run);
    filterRows(); icons();
    if (run && ["running", "cancelling"].includes(run.status)) {
      const pollingRunId = run.run_id;
      setTimeout(() => { if (state.tab === "results" && state.runId === pollingRunId) render(); }, 2000);
    }
  }

  function filterRows() {
    const q = document.getElementById("evSearch").value.toLowerCase(), status = document.getElementById("evStatus").value;
    state.threshold = Math.min(1, Math.max(0, Number(document.getElementById("evThreshold").value || .5)));
    const matchesStatus = item => {
      const score = item.scores?.score;
      if (!status) return true;
      if (["open", "processed", "verified", "ignored"].includes(status)) return item.error_book?.status === status;
      if (status === "error") return item.status === "error";
      if (status === "unscored") return score == null && item.status !== "error";
      if (status === "meets") return score != null && Number(score) >= state.threshold;
      if (status === "below") return score != null && Number(score) < state.threshold;
      return true;
    };
    const rows = state.results.filter(r => { const hay = `${r.question} ${r.gold_answer} ${r.answer} ${r.error_message}`.toLowerCase(); return (!q || hay.includes(q)) && matchesStatus(r); });
    state.filteredResults = rows;
    const issueLabel = value => ({ open: "待处理", processed: "已处理待复测", verified: "已验证", ignored: "已忽略" })[value] || "";
    document.getElementById("evReportRows").innerHTML = rows.length ? rows.map(r => {
      const s = r.scores || {};
      const resultLabel = r.status === "error" ? "调用异常" : s.score == null ? "未评分" : Number(s.score) >= state.threshold ? "达到分析阈值" : "答案未通过";
      const resultClass = r.status === "error" ? "bad" : s.score == null ? "" : Number(s.score) >= state.threshold ? "ok" : "warn";
      const treatment = issueLabel(r.error_book?.status);
      return `<tr class="ev-result-row" data-result-id="${r.result_id}" tabindex="0"><td><b>${esc(r.question)}</b><small>标准答案：${esc(r.gold_answer || "—")}</small></td><td><span class="ev-answer-preview">${esc(r.answer || r.error_message || "—")}</span></td><td>${s.score == null ? "—" : Math.round(s.score * 100)}</td><td>${s.latency_ms == null ? "—" : s.latency_ms + " ms"}</td><td><span class="es-tag ${resultClass}">${esc(resultLabel)}</span>${treatment ? `<small class="ev-treatment ${esc(r.error_book.status)}">${esc(treatment)}</small>` : ""}<small class="ev-row-hint">点击查看详情</small></td></tr>`;
    }).join("") : `<tr><td colspan="5" class="es-gen-hint">没有符合条件的结果。</td></tr>`;
    document.querySelectorAll(".ev-result-row").forEach(row => {
      row.onclick = () => openResultDetail(state.results.find(item => Number(item.result_id) === Number(row.dataset.resultId)));
      row.onkeydown = event => { if (["Enter", " "].includes(event.key)) { event.preventDefault(); row.click(); } };
    });
    refreshAnalysisMetrics();
  }

  const treatmentLabel = value => ({ open: "待处理", processed: "已处理待复测", verified: "已验证", ignored: "已忽略" })[value] || "未进入处理队列";
  const categoryLabel = value => ({ agent_answer: "智能体回答问题", request_config: "请求配置问题", dataset: "评测集内容问题", scoring: "评分规则问题", platform: "平台运行问题", unknown: "待进一步确认" })[value] || value || "未分类";

  async function openResultDetail(result) {
    if (!result) return;
    document.querySelectorAll(".ev-detail-mask").forEach(item => item.remove());
    const scores = result.scores || {}, issue = result.error_book;
    const scoreLabels = { score: "答案得分", em: "精确匹配", method: "评分方法", refusal_ok: "拒答判断", latency_ms: "调用耗时", tokens: "Token", cost: "成本", error: "调用错误" };
    const scoreRows = Object.entries(scores).filter(([, value]) => value != null && value !== "").map(([key, value]) => {
      const failed = key === "score" && Number(value) < state.threshold || key === "error" && value || typeof value === "boolean" && value === false;
      const shown = typeof value === "boolean" ? (value ? "是" : "否") : key === "score" ? Math.round(Number(value) * 100) : key === "latency_ms" ? `${value} ms` : value;
      return `<div class="ev-score-row ${failed ? "failed" : ""}"><span>${esc(scoreLabels[key] || key)}</span><b>${esc(shown)}</b>${failed ? '<i data-lucide="circle-x"></i>' : '<i data-lucide="circle-check"></i>'}</div>`;
    }).join("") || '<p class="es-gen-hint">本题没有可用评分项。</p>';
    const observable = result.status === "error" ? "调用异常" : scores.score == null ? "未评分" : Number(scores.score) >= state.threshold ? "达到分析阈值" : "答案未通过";
    const drawer = document.createElement("div"); drawer.className = "ev-detail-mask";
    drawer.innerHTML = `<aside class="ev-detail-drawer"><div class="ev-detail-head"><div><small>单题结果 #${result.result_id}</small><h3>${esc(observable)}</h3></div><button class="modal-x" aria-label="关闭">×</button></div><div class="ev-detail-body">
      <section><h4>评测样本</h4><dl class="ev-detail-list"><div><dt>问题</dt><dd>${esc(result.question)}</dd></div><div><dt>标准答案</dt><dd>${esc(result.gold_answer || "—")}</dd></div><div><dt>智能体回答</dt><dd>${esc(result.answer || result.error_message || "—")}</dd></div><div><dt>所属维度</dt><dd>${esc(result.dimension || "未标注")}</dd></div></dl></section>
      <section><h4>评分明细</h4><p class="ev-section-note">仅展示后端实际返回的评分项；红色项表示未达到当前分析阈值。</p><div class="ev-score-list">${scoreRows}</div></section>
      <section><div class="ev-section-title"><h4>异常处理</h4><span class="es-tag ${issue?.status === "verified" ? "ok" : issue?.status === "open" ? "bad" : "warn"}">${esc(treatmentLabel(issue?.status))}</span></div>${issue ? `<label class="es-field">人工分类<select class="es-input" id="evIssueCategory"><option value="">请选择</option>${[["agent_answer","智能体回答问题"],["request_config","请求配置问题"],["dataset","评测集内容问题"],["scoring","评分规则问题"],["platform","平台运行问题"],["unknown","待进一步确认"]].map(([value,label]) => `<option value="${value}" ${issue.resolution_category === value ? "selected" : ""}>${label}</option>`).join("")}</select></label><label class="es-field">处理备注<textarea class="es-input" id="evIssueNote" rows="3" placeholder="记录判断依据、修改内容或忽略原因">${esc(issue.resolution_note || "")}</textarea></label><div class="ev-treatment-actions"><button class="btn ghost" id="evIgnoreIssue">忽略</button><button class="btn primary" id="evProcessIssue">标记已处理，等待复测</button></div>` : '<p class="es-gen-hint">本题未进入异常处理队列。</p>'}</section>
      <section><div class="ev-section-title"><h4>复测记录</h4>${["error", "failed"].includes(result.status) || Number(scores.score) < state.threshold ? '<button class="btn ghost" id="evRetryCase"><i data-lucide="rotate-cw"></i>单题复测</button>' : ""}</div><div id="evAttemptList" class="ev-attempt-list"><span class="spinner"></span></div></section>
    </div></aside>`;
    document.body.appendChild(drawer); icons();
    const close = () => drawer.remove(); drawer.querySelector(".modal-x").onclick = close; drawer.onclick = event => { if (event.target === drawer) close(); };
    if (issue) {
      drawer.querySelector("#evProcessIssue").onclick = () => updateIssue(issue, "processed", drawer);
      drawer.querySelector("#evIgnoreIssue").onclick = () => updateIssue(issue, "ignored", drawer);
    }
    if (drawer.querySelector("#evRetryCase")) drawer.querySelector("#evRetryCase").onclick = () => openCaseRetry(result, drawer);
    await renderAttempts(result.result_id, drawer.querySelector("#evAttemptList"));
  }

  async function updateIssue(issue, status, drawer) {
    const category = drawer.querySelector("#evIssueCategory").value;
    const note = drawer.querySelector("#evIssueNote").value.trim();
    if (status === "processed" && !category) return toast("请先选择人工分类");
    if (status === "ignored" && !note) return toast("忽略异常时必须填写原因");
    try {
      const updated = await patch(`/api/error-book/${issue.item_id}`, { status, resolution_category: category || null, resolution_note: note || null });
      const result = state.results.find(item => item.error_book?.item_id === issue.item_id); if (result) result.error_book = updated;
      toast(status === "processed" ? "已处理，等待单题复测验证" : "已忽略；原始结果仍会保留");
      drawer.remove(); filterRows(); if (result) openResultDetail(result);
    } catch (error) { toast("更新失败：" + error.message); }
  }

  async function renderAttempts(resultId, target) {
    try {
      const data = await apiGet(`/api/evaluation-results/${resultId}/attempts`);
      const attempts = data.attempts || [];
      target.innerHTML = attempts.map(item => `<div class="ev-attempt"><span>#${item.attempt_no || 1}</span><div><b>${item.parent_result_id ? "单题复测" : "原始结果"}</b><small>${esc(formatDateTime(item.created_at))}</small></div><strong>${item.status === "pending" ? "执行中" : item.status === "error" ? "调用异常" : item.scores?.score == null ? "未评分" : Math.round(item.scores.score * 100) + " 分"}</strong></div>`).join("");
      icons();
      if (attempts.some(item => item.status === "pending")) setTimeout(() => { if (document.body.contains(target)) renderAttempts(resultId, target); }, 1500);
    } catch (error) { target.innerHTML = `<p class="es-gen-hint">复测记录加载失败：${esc(error.message)}</p>`; }
  }

  function openCaseRetry(result, drawer) {
    const run = state.runs.find(item => Number(item.run_id) === Number(result.run_id));
    const profiles = loadProfiles().filter(item => item.adapter === run?.adapter);
    const modal = document.createElement("div"); modal.className = "modal-mask ev-retry-mask";
    modal.innerHTML = `<div class="modal ev-retry-modal"><div class="modal-head"><span>单题复测</span><button class="modal-x">×</button></div><div class="modal-body"><p class="es-gen-hint">复测会创建新的尝试记录，不覆盖原始结果。请选择复用配置并补充不会被保存的敏感字段。</p><label class="es-field">复用配置<select class="es-input" id="evRetryProfile"><option value="">使用运行中的非敏感配置</option>${profiles.map(item => `<option value="${item.id}">${esc(item.name)}</option>`).join("")}</select></label>${run?.adapter === "http" ? '<label class="es-field">请求头（JSON）<textarea class="es-input ev-code" id="evRetrySecret" rows="3" placeholder=\'{"Authorization":"Bearer ..."}\'></textarea></label>' : '<label class="es-field">API Key<input class="es-input" id="evRetrySecret" type="password" placeholder="留空则使用后端环境配置"/></label>'}</div><div class="modal-foot"><button class="btn ghost modal-cancel">取消</button><button class="btn primary" id="evRetryConfirm"><i data-lucide="rotate-cw"></i>开始复测</button></div></div>`;
    document.body.appendChild(modal); icons(); const close = () => modal.remove(); modal.querySelector(".modal-x").onclick = close; modal.querySelector(".modal-cancel").onclick = close;
    modal.querySelector("#evRetryConfirm").onclick = async event => {
      const profile = profiles.find(item => item.id === modal.querySelector("#evRetryProfile").value);
      const cfg = { ...(run?.adapter_config || {}), ...(profile?.config || {}) };
      const secret = modal.querySelector("#evRetrySecret").value.trim();
      if (run?.adapter === "http" && secret) { try { cfg.headers = JSON.parse(secret); } catch { return toast("请求头必须是合法 JSON"); } }
      if (run?.adapter === "openai_compatible" && secret) cfg.api_key = secret;
      event.currentTarget.disabled = true;
      try { await post(`/api/evaluation-results/${result.result_id}/retry`, { adapter_config: cfg, analysis_threshold: state.threshold }); toast("单题复测已开始"); close(); const target = drawer.querySelector("#evAttemptList"); if (target) renderAttempts(result.result_id, target); }
      catch (error) { toast("复测失败：" + error.message); event.currentTarget.disabled = false; }
    };
  }

  async function cancelRun(run) {
    if (!confirm(`确认取消“${run.name || `运行 #${run.run_id}`}”？当前单题请求结束后将停止。`)) return;
    try { await post(`/api/evaluation-runs/${run.run_id}/cancel`, {}); toast("已提交取消请求"); render(); }
    catch (error) { toast("取消失败：" + error.message); }
  }

  function openRunComparison(run, runs) {
    const candidates = runs.filter(item => Number(item.composition_id) === Number(run.composition_id) && item.run_id !== run.run_id && item.status === "done");
    if (!candidates.length) return toast("同一评测集版本下暂无可对比的已完成运行");
    const modal = document.createElement("div"); modal.className = "modal-mask";
    modal.innerHTML = `<div class="modal ev-compare-modal"><div class="modal-head"><span>同版本运行对比</span><button class="modal-x">×</button></div><div class="modal-body"><div class="ev-compare-picker"><div><small>当前运行</small><b>${esc(run.name || `运行 #${run.run_id}`)}</b></div><i data-lucide="arrow-left-right"></i><label class="es-field">对比运行<select class="es-input" id="evCompareTarget">${candidates.map(item => `<option value="${item.run_id}">${esc(item.name || `运行 #${item.run_id}`)}</option>`).join("")}</select></label></div><div id="evCompareBody" class="ev-compare-body"><p class="es-gen-hint">选择运行后查看新增失败、已修复和持续失败。</p></div></div><div class="modal-foot"><button class="btn primary modal-x2">关闭</button></div></div>`;
    document.body.appendChild(modal); icons(); const close = () => modal.remove(); modal.querySelector(".modal-x").onclick = close; modal.querySelector(".modal-x2").onclick = close;
    const compare = async () => {
      const targetRun = candidates.find(item => Number(item.run_id) === Number(modal.querySelector("#evCompareTarget").value));
      const body = modal.querySelector("#evCompareBody"); body.innerHTML = '<span class="spinner"></span>';
      try {
        const data = await apiGet(`/api/evaluation-runs/${targetRun.run_id}/results`), other = data.results || [];
        const currentMap = new Map(state.results.map(item => [item.case_uid, item])), otherMap = new Map(other.map(item => [item.case_uid, item]));
        const failed = item => item.status === "error" || item.scores?.score != null && Number(item.scores.score) < state.threshold;
        const rows = [...new Set([...currentMap.keys(), ...otherMap.keys()])].map(key => ({ key, current: currentMap.get(key), other: otherMap.get(key) }));
        const regressions = rows.filter(item => !failed(item.other || {}) && failed(item.current || {}));
        const fixes = rows.filter(item => failed(item.other || {}) && !failed(item.current || {}));
        const persistent = rows.filter(item => failed(item.other || {}) && failed(item.current || {}));
        const a = analysisStats(state.results), b = analysisStats(other);
        body.innerHTML = `<div class="ev-compare-kpis"><div><small>分析通过率变化</small><b>${b.scored ? Math.round(b.passed/b.scored*100) : 0}% → ${a.scored ? Math.round(a.passed/a.scored*100) : 0}%</b></div><div><small>新增失败</small><b class="bad">${regressions.length}</b></div><div><small>已修复</small><b class="ok">${fixes.length}</b></div><div><small>持续失败</small><b>${persistent.length}</b></div></div><div class="ev-compare-list">${[["新增失败",regressions,"bad"],["已修复",fixes,"ok"],["持续失败",persistent,"warn"]].map(([label,items,kind]) => `<section><h4>${label}<span>${items.length}</span></h4>${items.slice(0,20).map(item => `<div><span>${esc(item.current?.question || item.other?.question || item.key)}</span><b class="${kind}">${item.current?.scores?.score == null ? "—" : Math.round(item.current.scores.score*100)}</b></div>`).join("") || '<p class="es-gen-hint">暂无</p>'}</section>`).join("")}</div>`;
      } catch (error) { body.innerHTML = `<p class="es-gen-hint">对比加载失败：${esc(error.message)}</p>`; }
    };
    modal.querySelector("#evCompareTarget").onchange = compare; compare();
  }

  async function exportReport() {
    if (!state.runId) return;
    const filteredOnly = document.getElementById("evExportFiltered").checked;
    if (filteredOnly && !state.filteredResults.length) return toast("当前筛选条件下没有可导出的结果");
    const button = document.getElementById("evExportConfirm");
    button.disabled = true;
    button.textContent = "正在生成…";
    try {
      const response = await fetch(`${API_BASE}/api/evaluation-runs/${state.runId}/export`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ result_ids: filteredOnly ? state.filteredResults.map(item => item.result_id) : null }),
      });
      if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.detail || response.status); }
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      const filename = encodedName ? decodeURIComponent(encodedName) : `评测报告-${state.runId}.xlsx`;
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
      URL.revokeObjectURL(url);
      document.getElementById("evExportPopover").hidden = true;
      toast(filteredOnly ? "已导出当前筛选结果" : "已导出全部原始报告");
    } catch (error) { toast("导出失败：" + error.message); }
    finally { button.disabled = false; button.innerHTML = '<i data-lucide="file-spreadsheet"></i>导出 Excel'; icons(); }
  }

  function openRunMenu(run, anchor) {
    if (!run) return;
    closeRunMenu();
    const menu = document.createElement("div");
    menu.className = "ctx-popup ev-run-menu";
    const active = ["pending", "running", "cancelling"].includes(run.status);
    menu.innerHTML = `<button data-ev-act="export"><i data-lucide="download"></i>导出</button>${active ? `<button data-ev-act="cancel" ${run.status === "cancelling" ? "disabled" : ""}><i data-lucide="square"></i>${run.status === "cancelling" ? "取消中" : "取消运行"}</button>` : '<button data-ev-act="delete" class="danger"><i data-lucide="trash-2"></i>永久删除</button>'}`;
    document.body.appendChild(menu);
    const rect = anchor.getBoundingClientRect();
    const menuW = 132, menuH = 78;
    let top = rect.bottom + 4, left = rect.right - menuW;
    if (left < 8) left = 8;
    if (top + menuH > window.innerHeight - 8) top = rect.top - menuH - 4;
    menu.style.top = top + "px"; menu.style.left = left + "px";
    icons();
    menu.querySelector('[data-ev-act="export"]').onclick = e => { e.stopPropagation(); closeRunMenu(); exportRun(run.run_id); };
    const cancel = menu.querySelector('[data-ev-act="cancel"]'); if (cancel && !cancel.disabled) cancel.onclick = e => { e.stopPropagation(); closeRunMenu(); cancelRun(run); };
    const remove = menu.querySelector('[data-ev-act="delete"]'); if (remove) remove.onclick = e => { e.stopPropagation(); closeRunMenu(); openDeleteRun(run); };
  }

  function openDeleteRun(run) {
    const modal = document.createElement("div"); modal.className = "modal-mask";
    modal.innerHTML = `<div class="modal ev-delete-modal"><div class="modal-head"><span>永久删除运行</span><button class="modal-x">×</button></div><div class="modal-body"><div class="ev-danger-note"><i data-lucide="triangle-alert"></i><div><b>该操作不可恢复</b><p>运行、全部单题结果和异常处理记录都会被永久删除。</p></div></div><label class="es-field">再次确认：输入“永久删除”<input class="es-input" id="evDeletePhrase" autocomplete="off" placeholder="永久删除"/></label></div><div class="modal-foot"><button class="btn ghost modal-cancel">取消</button><button class="btn danger" id="evDeleteConfirm" disabled>永久删除</button></div></div>`;
    document.body.appendChild(modal); icons(); const close = () => modal.remove(); modal.querySelector(".modal-x").onclick = close; modal.querySelector(".modal-cancel").onclick = close;
    const input = modal.querySelector("#evDeletePhrase"), button = modal.querySelector("#evDeleteConfirm"); input.oninput = () => button.disabled = input.value !== "永久删除";
    button.onclick = async () => {
      button.disabled = true;
      try {
        const response = await fetch(`${API_BASE}/api/evaluation-runs/${run.run_id}?confirm=true`, { method: "DELETE" });
        if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.detail || response.status); }
        close(); toast(`已永久删除运行 #${run.run_id}`); if (state.runId === run.run_id) state.runId = null; render();
      } catch (error) { toast("删除失败：" + error.message); button.disabled = false; }
    };
  }
  function closeRunMenu() {
    document.querySelectorAll(".ev-run-menu").forEach(m => m.remove());
  }
  async function exportRun(runId) {
    try {
      const response = await fetch(`${API_BASE}/api/evaluation-runs/${runId}/export`, {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ result_ids: null }),
      });
      if (!response.ok) { const error = await response.json().catch(() => ({})); throw new Error(error.detail || response.status); }
      const blob = await response.blob();
      const disposition = response.headers.get("Content-Disposition") || "";
      const encodedName = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
      const filename = encodedName ? decodeURIComponent(encodedName) : `评测报告-${runId}.xlsx`;
      const url = URL.createObjectURL(blob), link = document.createElement("a");
      link.href = url; link.download = filename; document.body.appendChild(link); link.click(); link.remove();
      URL.revokeObjectURL(url);
      toast("已导出该运行报告");
    } catch (error) { toast("导出失败：" + error.message); }
  }

  async function render() {
    if (!$w()) return;
    shell(`<div class="card card-pad ev-load-state"><span class="spinner"></span><div><b>正在加载${state.tab === "config" ? "评测配置" : "评测结果"}</b><p class="es-gen-hint">正在连接后端并同步最新数据…</p></div></div>`);
    try {
      if (state.tab === "config") await config(); else await results();
    } catch (error) {
      shell(`<div class="card card-pad ev-load-state ev-load-error"><span><i data-lucide="cloud-alert"></i></span><div><b>数据加载失败</b><p class="es-gen-hint">${esc(error.message || "无法连接后端服务")}</p><button class="btn ghost" id="evRetryLoad"><i data-lucide="refresh-cw"></i>重新加载</button></div></div>`);
      document.getElementById("evRetryLoad").onclick = render;
      icons();
    }
  }
  window.renderEvaluation = render;
  document.addEventListener("click", e => {
    const tab = e.target.closest("[data-ev-tab]");
    if (tab) { state.tab = tab.dataset.evTab; render(); }
    if (e.target.closest("#evConfigBtn")) { state.tab = "config"; render(); }
    const popover = document.getElementById("evExportPopover");
    if (popover && !e.target.closest(".ev-export-wrap")) popover.hidden = true;
    if (!e.target.closest(".ev-run-menu") && !e.target.closest(".tree-dots")) closeRunMenu();
  });
})();
