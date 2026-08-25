/* 评测工作台：配置与结果两个二级页面。 */
(() => {
  const state = window.__evWorkspace = window.__evWorkspace || {
    tab: "config",
    compositionId: null,
    runId: null,
    results: [],
    filteredResults: [],
    threshold: .5,
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
  const runStatusLabel = status => ({ pending: "等待中", running: "运行中", done: "已完成", failed: "失败" })[status] || status || "未知";
  const caseStatusLabel = status => ({ passed: "通过", failed: "未通过", error: "异常", unscored: "未评分", pending: "等待中" })[status] || status || "—";

  function shell(content, sideExtra) {
    $w().innerHTML = `<div class="ev-layout"><aside class="ev-side"><button class="ev-side-item ${state.tab === "config" ? "on" : ""}" data-ev-tab="config"><i data-lucide="sliders-horizontal"></i><span>评测配置</span></button><button class="ev-side-item ${state.tab === "results" ? "on" : ""}" data-ev-tab="results"><i data-lucide="chart-no-axes-combined"></i><span>评测结果</span></button>${sideExtra || ""}</aside><div class="ev-main">${content}</div></div>`;
    icons();
  }

  async function config() {
    const compositions = await apiGet("/api/compositions");
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

  function metrics(summary, rows) {
    const total = summary.total || rows.length, passed = summary.passed || 0, error = summary.error_count || 0;
    const avg = rows.length ? Math.round(rows.reduce((n, x) => n + Number((x.scores || {}).latency_ms || 0), 0) / rows.length) : 0;
    return `<div class="ev-kpis"><div><span class="ev-kpi-ic"><i data-lucide="list-checks"></i></span><small>总题数</small><b>${total}</b></div><div><span class="ev-kpi-ic"><i data-lucide="badge-check"></i></span><small>通过率</small><b>${total ? Math.round(passed / total * 100) : 0}%</b></div><div><span class="ev-kpi-ic"><i data-lucide="timer"></i></span><small>平均用时</small><b>${avg} ms</b></div><div><span class="ev-kpi-ic"><i data-lucide="circle-alert"></i></span><small>异常数</small><b>${error}</b></div></div>`;
  }

  async function results() {
    const [runs, compositions] = await Promise.all([
      apiGet("/api/evaluation-runs"),
      apiGet("/api/compositions"),
    ]);
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
        const icon = item.status === "done" ? "circle-check" : item.status === "failed" ? "circle-x" : item.status === "running" ? "loader" : "clock";
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
    const progress = run && run.status === "running" ? `<section class="ev-progress-card"><div class="ev-progress-head"><div><span class="ev-running-dot"></span><b>评测执行中</b><small>完成后将自动刷新指标与原始报告</small></div><strong>${Number(run.progress || 0)}%</strong></div><div class="ev-bar"><span style="width:${Number(run.progress || 0)}%"></span></div><div class="ev-progress-meta"><span>${Number(run.finished || 0)} / ${Number(run.total || 0)} 题</span><span><i data-lucide="clock-3"></i>预计剩余 ${esc(estimateRemaining(run))}</span></div></section>` : "";
    const content = run ? `<div class="ev-result-title"><div><span class="es-tag">${esc(runStatusLabel(run.status))}</span><h2>${esc(run.name || `运行 #${run.run_id}`)}</h2><p>${esc(selectedComposition?.name || `评测集 #${run.composition_id}`)} · 版本 #${esc(run.composition_id)} · ${esc(formatDateTime(run.created_at))}</p></div><label class="ev-threshold">通过阈值<input class="es-input" id="evThreshold" type="number" min="0" max="1" step=".05" value="${state.threshold}"/></label></div>${progress}${metrics(data.summary || {}, state.results)}<div class="card card-pad ev-report"><div class="ev-report-head"><div><div class="card-t">原始评测报告</div><p>完整保留问题、标准答案、智能体回答、评分与归因信息。</p></div><div class="ev-export-wrap"><button class="btn ghost" id="evExportToggle"><i data-lucide="download"></i>导出报告<i data-lucide="chevron-down"></i></button><div class="ev-export-popover" id="evExportPopover" hidden><label><input type="checkbox" id="evExportFiltered"/>仅导出当前筛选结果</label><small>默认导出当前运行的全部原始报告</small><button class="btn primary" id="evExportConfirm"><i data-lucide="file-spreadsheet"></i>导出 Excel</button></div></div></div><div class="ev-filters"><input class="es-input" id="evSearch" placeholder="搜索问题、标准答案或智能体回答"/><select class="es-input" id="evStatus"><option value="">全部状态</option><option value="passed">通过</option><option value="failed">未通过</option><option value="error">异常</option><option value="diagnosis">有 ErrorBook</option></select></div><div class="ev-table-wrap"><table class="ev-table"><thead><tr><th>问题 / 标准答案</th><th>智能体回答 A'</th><th>得分</th><th>耗时</th><th>状态 / 归因</th></tr></thead><tbody id="evReportRows"></tbody></table></div></div>` : `<div class="ev-result-empty"><span><i data-lucide="chart-no-axes-combined"></i></span><h2>选择一次评测运行</h2><p>从左侧「评测结果目录」中展开并选择运行，即可查看指标和原始报告。</p><button class="btn primary" id="evConfigBtn">前往评测配置</button></div>`;
    shell(`<div class="ev-results-layout ev-results-single"><div class="ev-result-content">${content}</div></div>`, catalog);
    // 仿评测集库目录交互（事件委托到稳定的父容器，子节点重建也不丢监听）
    const catalogEl = $w().querySelector(".ev-side-catalog");
    if (catalogEl) {
      catalogEl.onclick = (e) => {
        const dot = e.target.closest(".tree-dots[data-run-dots]");
        if (dot) {
          e.stopPropagation();
          openRunMenu(Number(dot.dataset.runDots), dot);
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
    filterRows(); icons();
    if (run && run.status === "running") {
      const pollingRunId = run.run_id;
      setTimeout(() => { if (state.tab === "results" && state.runId === pollingRunId) render(); }, 2000);
    }
  }

  function filterRows() {
    const q = document.getElementById("evSearch").value.toLowerCase(), status = document.getElementById("evStatus").value;
    state.threshold = Number(document.getElementById("evThreshold").value || .5);
    const rows = state.results.filter(r => { const hay = `${r.question} ${r.gold_answer} ${r.answer}`.toLowerCase(); return (!q || hay.includes(q)) && (!status || (status === "diagnosis" ? r.diagnosis : r.status === status)); });
    state.filteredResults = rows;
    document.getElementById("evReportRows").innerHTML = rows.length ? rows.map(r => { const s = r.scores || {}, diagnosis = typeof r.diagnosis === "string" ? r.diagnosis : r.diagnosis?.root_cause; return `<tr><td><b>${esc(r.question)}</b><small>标准答案：${esc(r.gold_answer || "—")}</small></td><td>${esc(r.answer || r.error_message || "—")}</td><td>${s.score == null ? "—" : Math.round(s.score * 100) + ""}</td><td>${s.latency_ms == null ? "—" : s.latency_ms + " ms"}</td><td><span class="es-tag ${r.status === "passed" ? "ok" : r.status === "error" ? "bad" : "warn"}">${esc(caseStatusLabel(r.status))}</span>${diagnosis ? `<small class="ev-errorbook">${esc(diagnosis)}</small>` : ""}</td></tr>`; }).join("") : `<tr><td colspan="5" class="es-gen-hint">没有符合条件的结果。</td></tr>`;
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

  function openRunMenu(runId, anchor) {
    closeRunMenu();
    const menu = document.createElement("div");
    menu.className = "ctx-popup ev-run-menu";
    menu.innerHTML = `<button data-ev-act="export"><i data-lucide="download"></i>导出</button><button data-ev-act="delete" class="danger"><i data-lucide="trash-2"></i>删除</button>`;
    document.body.appendChild(menu);
    const rect = anchor.getBoundingClientRect();
    const menuW = 132, menuH = 78;
    let top = rect.bottom + 4, left = rect.right - menuW;
    if (left < 8) left = 8;
    if (top + menuH > window.innerHeight - 8) top = rect.top - menuH - 4;
    menu.style.top = top + "px"; menu.style.left = left + "px";
    icons();
    menu.querySelector('[data-ev-act="export"]').onclick = e => { e.stopPropagation(); closeRunMenu(); exportRun(runId); };
    menu.querySelector('[data-ev-act="delete"]').onclick = e => {
      e.stopPropagation(); closeRunMenu();
      if (!confirm(`确认删除运行 #${runId}？该操作将同时删除其全部单题结果与失败本记录，不可恢复。`)) return;
      fetch(`${API_BASE}/api/evaluation-runs/${runId}`, { method: "DELETE" })
        .then(async r => { if (!r.ok) { const e = await r.json().catch(() => ({})); throw new Error(e.detail || r.status); } return r.json(); })
        .then(() => { toast(`已删除运行 #${runId}`); if (state.runId === runId) state.runId = null; render(); })
        .catch(err => toast("删除失败：" + (err.message || err)));
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
