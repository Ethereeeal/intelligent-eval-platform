/* ============ 评测运行（m08） ============
   完整流程：
   1) 目标智能体调用方式配置：适配器(示例模拟 / OpenAI 兼容接口) + 配置项(接口地址/密钥/模型/系统提示词)
   2) 选择评测集：固定一个来源（生成库/公共库/上传库）或勾选多个来源合并
      （前端把多个 source 组装成一个组合的多个条目，调 /api/compositions 建临时组合）
   3) 开始异步调用跑批：POST /api/evaluation-runs（后端线程异步执行，状态 跑批中）
   4) 自动调取结果：轮询 run 状态，跑批中 → 完成 后拉 results + summary
   5) 生成对比结果：问题 Q / 金标准答案 A / 目标智能体回答 A'，自动评分(分数/判定) + 诊断
   6) 展示结果：分层指标 + 逐题对比卡片（问题/金标准/目标回答/评分/诊断）

   评测集来源映射：
     生成库 → {source:"doc_generated", version_id}（含冻结版本与组合）
     public  → {source:"public", set_id}
     uploaded→ {source:"uploaded", set_id} */

const apiPostEV = async (path, body) => {
  const res = await fetch(API_BASE + path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  if (!res.ok) {
    let detail = res.status;
    try { detail = (await res.json()).detail || detail; } catch (e) {}
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
  return res.json();
};

let __evTimer = null;

// 状态中文映射
const EV_STATUS_CN = {
  done: "完成", running: "跑批中", failed: "失败",
  passed: "通过", failed: "未通过", error: "错误", unscored: "未评分",
};
const EV_ADAPTER_CN = {
  mock: "示例模拟", openai_compatible: "OpenAI 兼容接口",
};
// 指标 key 中文映射
const EV_METRIC_CN = {
  total: "总题数", scored: "已评分", passed: "通过数",
  passed_rate: "通过率", error_count: "错误数", error_rate: "错误率",
  diagnosis_distribution: "诊断分布",
  by_difficulty: "按难度", by_dimension: "按维度",
  total_latency_ms: "总耗时(毫秒)", total_tokens: "总Token数", total_cost: "总成本",
};
// 来源中文名
function evSourceName(item) {
  return ({ composition: "组合", public: "公共库", uploaded: "上传库", doc_generated: "生成库" })[item.source] || item.source;
}

// ---------- 渲染入口 ----------
async function renderEvaluation() {
  const view = window.__evView || "runs";
  $$("#evViewSeg .seg button").forEach(b => b.classList.toggle("on", b.dataset.ev === view));
  $("#evRuns").hidden = view !== "runs";
  $("#evDetail").hidden = view !== "detail";
  $("#evErrorbook").hidden = view !== "errorbook";

  if (view === "runs") await evLoadRuns();
  if (view === "errorbook") await evLoadErrorBook();
  if (view === "detail" && window.__evOpenId) await evRefreshDetail(window.__evOpenId);
  if (view === "detail" && !window.__evOpenId) $("#evDetailBox").innerHTML = `<div class="es-gen-hint">从「运行列表」点击一条查看进度与单题结果。</div>`;
  icons();
}

// ---------- 运行列表 ----------
async function evLoadRuns() {
  const box = $("#evRunList");
  box.innerHTML = `<div class="es-gen-hint">加载中…</div>`;
  try {
    const runs = await apiGet(`/api/evaluation-runs`).catch(() => []);
    if (!runs.length) {
      box.innerHTML = `<div class="es-gen-hint">暂无评测运行。点击右上角「发起评测」配置目标智能体并选择评测集。</div>`;
      return;
    }
    box.innerHTML = runs.map(r => `<div class="list-row expandable" data-run="${r.run_id}">
      <span class="st" style="--c:${r.status === "done" ? "#1B8A5A" : r.status === "failed" ? "#C0392B" : "#1B6CA8"}"></span>
      <div class="lr-tx">
        <div class="lr-q">${r.name || ("运行 #" + r.run_id)}</div>
        <div class="lr-m">#${r.run_id} · 组合 #${r.composition_id} · ${EV_ADAPTER_CN[r.adapter] || r.adapter} · ${EV_STATUS_CN[r.status] || r.status} · ${r.total || r.finished || 0} 题</div>
      </div>
      <button class="btn ghost ev-open" data-run="${r.run_id}"><i data-lucide="arrow-right"></i>详情</button>
    </div>`).join("");
  } catch (e) {
    box.innerHTML = `<div class="es-gen-hint">加载失败：${e.message}</div>`;
  }
}

// ---------- 运行详情（进度 + 对比结果） ----------
async function evOpenDetail(runId) {
  window.__evOpenId = runId;
  window.__evView = "detail";
  $$("#evViewSeg .seg button").forEach(b => b.classList.toggle("on", b.dataset.ev === "detail"));
  $("#evRuns").hidden = true; $("#evDetail").hidden = false; $("#evErrorbook").hidden = true;
  await evRefreshDetail(runId);
}

async function evRefreshDetail(runId, auto = true) {
  const box = $("#evDetailBox");
  box.innerHTML = `<div class="es-gen-hint">加载中…</div>`;
  try {
    const data = await apiGet(`/api/evaluation-runs/${runId}`).catch(() => null);
    if (!data) { box.innerHTML = `<div class="es-gen-hint">运行不存在或加载失败。</div>`; return; }
    const run = data.run || data;
    const summary = data.summary || {};

    if (run.status === "running") {
      box.innerHTML = `<div class="ev-progress">
        <div class="ev-bar"><span style="width:${run.progress || 0}%"></span></div>
        <div class="ev-progress-t">异步跑批中… ${run.finished || 0}/${run.total || 0}（${run.progress || 0}%）</div>
      </div>
      <div class="es-gen-hint">完成后将自动刷新并展示对比结果（Q / A / A'）。</div>`;
      if (auto) { clearTimeout(__evTimer); __evTimer = setTimeout(() => evRefreshDetail(runId, true), 2000); }
      icons();
      return;
    }

    const results = await apiGet(`/api/evaluation-runs/${runId}/results`).catch(() => ({ results: [], summary: {} }));
    const items = results.results || [];
    const s = results.summary || summary || {};
    // 指标翻译：key 中文化，数值按比例/百分比格式化
    const fmtVal = (k, v) => {
      if (k === "diagnosis_distribution" && typeof v === "object") {
        return Object.entries(v).map(([dk, dv]) => `${dk || "其他"}: ${dv}`).join("；");
      }
      if (k === "by_difficulty" || k === "by_dimension") {
        return Object.entries(v).map(([bk, bv]) =>
          `${bk}: ${bv.passed}/${bv.total}`).join("；");
      }
      if (typeof v === "number") {
        if ((k === "passed_rate" || k === "error_rate") && v != null) return (v * 100).toFixed(1) + "%";
        if (v <= 1 && v > 0) return (v * 100).toFixed(1) + "%";
        return v.toFixed ? (Number.isInteger(v) ? v : v.toFixed(2)) : v;
      }
      return v;
    };
    const metrics = Object.entries(s).map(([k, v]) =>
      `<span class="es-tag">${EV_METRIC_CN[k] || k}：${fmtVal(k, v)}</span>`).join("");

    const cards = items.map((it, i) => {
      const sc = it.scores || {};
      const st = it.status || "?";
      const badge = st === "passed" ? "ok" : (st === "failed" || st === "error") ? "bad" : "warn";
      const scoreTxt = sc.score != null ? `评分 ${(sc.score * 100).toFixed(0)}` : "无金标准";
      const diag = it.diagnosis && it.diagnosis.root_cause ? `<div class="ev-diag"><b>诊断：</b>${it.diagnosis.root_cause}</div>` : "";
      return `<div class="ev-card">
        <div class="ev-card-h"><span class="es-tag ${badge}">${EV_STATUS_CN[st] || st}</span><span class="es-tag">${scoreTxt}</span><span class="ev-dim">${it.dimension || ""} · ${it.difficulty || ""}</span></div>
        <div class="ev-qa"><span class="ev-lbl">问题</span><div class="ev-txt">${it.question || ""}</div></div>
        <div class="ev-qa"><span class="ev-lbl a">金标准</span><div class="ev-txt">${it.gold_answer || "（无金标准）"}</div></div>
        <div class="ev-qa"><span class="ev-lbl a2">目标回答</span><div class="ev-txt">${it.answer || "（未返回）"}</div></div>
        ${diag}
      </div>`;
    }).join("");

    box.innerHTML = `<div class="es-gen-hint">状态：<b>${EV_STATUS_CN[run.status] || run.status}</b> · 适配器 ${EV_ADAPTER_CN[run.adapter] || run.adapter} · 共 ${items.length} 题</div>
      <div class="ev-metrics">${metrics || '<span class="es-gen-hint">暂无分层指标</span>'}</div>
      <div class="ev-cards">${cards || '<div class="es-gen-hint">暂无单题结果</div>'}</div>`;
  } catch (e) {
    box.innerHTML = `<div class="es-gen-hint">加载失败：${e.message}</div>`;
  }
  icons();
}

// ---------- 失败本 ----------
async function evLoadErrorBook() {
  const box = $("#evErrorList");
  box.innerHTML = `<div class="es-gen-hint">加载中…</div>`;
  try {
    const items = await apiGet(`/api/error-book`).catch(() => []);
    if (!items.length) {
      box.innerHTML = `<div class="es-gen-hint">失败本为空，暂无智能体失败诊断记录。</div>`;
      return;
    }
    box.innerHTML = items.map(it => `<div class="list-row">
      <span class="st" style="--c:#C0392B"></span>
      <div class="lr-tx"><div class="lr-q">${it.case_uid || ""}</div>
      <div class="lr-m">${(it.diagnosis && it.diagnosis.root_cause) || it.note || ""}</div></div>
      <span class="es-tag bad">${(it.diagnosis && it.diagnosis.category) || ""}</span>
    </div>`).join("");
  } catch (e) {
    box.innerHTML = `<div class="es-gen-hint">加载失败：${e.message}</div>`;
  }
}

// ---------- 发起评测（配置 + 选集 + 合并 + 异步跑批） ----------
async function evStartRun() {
  const preset = window.__evPreset || null;
  window.__evPreset = null;

  let compositions = [], publicSets = [], uploadedSets = [], versions = [];
  try {
    [compositions, publicSets, uploadedSets, versions] = await Promise.all([
      apiGet(`/api/compositions`).catch(() => []),
      apiGet(`/api/public-sets`).catch(() => []),
      apiGet(`/api/eval-sets/uploaded`).catch(() => []),
      apiGet(`/api/versions`).catch(() => []),
    ]);
  } catch (e) { toast("加载来源失败：" + e.message); return; }

  const frozen = (versions || []).filter(v => v.status === "frozen");
  // 生成库 = 组合 + 冻结版本；上传集 → 上传库
  const groups = [
    { label: "生成库", items: [
      ...(compositions || []).map(c => ({ id: c.composition_id, name: c.name || ("组合 #" + c.composition_id), kind: "composition" })),
      ...(frozen || []).map(v => ({ id: v.version_id, name: v.name || ("版本 #" + v.version_id), kind: "doc" })),
    ] },
    { label: "金融通用 / 风险合规公共库", items: (publicSets || []).map(s => ({ id: s.set_id, name: s.name || ("公共库 #" + s.set_id), kind: "public" })) },
    { label: "上传库", items: (uploadedSets || []).map(s => ({ id: s.set_id, name: s.name || ("上传库 #" + s.set_id), kind: "uploaded" })) },
  ];
  const presetVal = preset ? `${preset.source}:${preset.version_id || preset.set_id}` : null;
  const srcOptions = groups.map(g => `<optgroup label="${g.label}">` + g.items.map(it => {
    const val = `${it.kind === "doc" ? "doc" : it.kind}:${it.id}`;
    return `<option value="${val}" ${val === presetVal ? "selected" : ""}>${it.name}</option>`;
  }).join("") + `</optgroup>`).join("");

  const modal = document.createElement("div");
  modal.className = "modal-mask";
  modal.innerHTML = `<div class="modal modal-wide">
    <div class="modal-head"><span>发起评测运行</span><button class="modal-x">×</button></div>
    <div class="modal-body">
      <div class="ev-form-grid">
        <div>
          <label class="es-field">① 目标智能体调用方式</label>
          <select id="evAdapter" class="es-input">
            <option value="mock">mock（示例回答，离线演示）</option>
            <option value="openai_compatible">OpenAI 兼容接口</option>
          </select>
          <div id="evAdapterCfg" class="ev-cfg">
            <label class="es-field">API Base</label><input id="evApiBase" class="es-input" placeholder="https://.../v1" />
            <label class="es-field">API Key</label><input id="evApiKey" class="es-input" type="password" placeholder="sk-..." />
            <label class="es-field">Model</label><input id="evModel" class="es-input" placeholder="gpt-4o / 自建模型名" />
            <label class="es-field">System Prompt（可选）</label><textarea id="evSys" class="es-input" rows="2" placeholder="你是业务问答助手…"></textarea>
          </div>
        </div>
        <div>
          <label class="es-field">② 选择评测集（可勾选多个合并）</label>
          <div id="evSrcList" class="ev-src-list">${groups.map(g => `<div class="ev-src-group"><div class="ev-src-gl">${g.label}</div>` + g.items.map(it => `<label class="ev-src-item"><input type="checkbox" value="${it.kind === "doc" ? "doc" : it.kind}:${it.id}" /> ${it.name}</label>`).join("") + `</div>`).join("")}</div>
          <div class="ev-preset-note" id="evPresetNote"></div>
        </div>
      </div>
      <label class="es-field">运行名称（可选）</label>
      <input id="evName" class="es-input" placeholder="留空自动命名" />
    </div>
    <div class="modal-foot"><button class="btn ghost modal-cancel">取消</button><button class="btn primary" id="evConfirm"><i data-lucide="play"></i>开始异步跑批</button></div>
  </div>`;
  document.body.appendChild(modal);
  icons();

  const close = () => modal.remove();
  modal.querySelector(".modal-x").onclick = close;
  modal.querySelector(".modal-cancel").onclick = close;
  modal.addEventListener("click", e => { if (e.target === modal) close(); });
  modal.querySelector("#evAdapter").onchange = e => {
    modal.querySelector("#evAdapterCfg").style.display = e.target.value === "mock" ? "none" : "block";
  };
  if (presetVal) modal.querySelector("#evPresetNote").innerHTML = `<div class="es-gen-hint">已预选来源：${evSourceName({ source: preset.source })} #${preset.version_id || preset.set_id}。可在右侧勾选更多以合并。</div>`;

  modal.querySelector("#evConfirm").onclick = async () => {
    const adapter = modal.querySelector("#evAdapter").value;
    const checked = [...modal.querySelectorAll("#evSrcList input:checked")].map(c => c.value);
    // 预选存在但用户未勾选时，用预选
    const sel = checked.length ? checked : (presetVal ? [presetVal] : []);
    if (!sel.length) { toast("请至少选择一个评测集"); return; }
    const name = modal.querySelector("#evName").value.trim();
    const cfg = adapter === "openai_compatible" ? {
      api_base: modal.querySelector("#evApiBase").value.trim(),
      api_key: modal.querySelector("#evApiKey").value.trim(),
      model: modal.querySelector("#evModel").value.trim(),
      system_prompt: modal.querySelector("#evSys").value.trim() || null,
    } : null;

    try {
      // 组装 composition items（支持多集合并）
      const items = sel.map(v => {
        const [type, idStr] = v.split(":");
        const id = Number(idStr);
        return type === "composition" ? { source: "composition", composition_id: id }
          : type === "public" ? { source: "public", set_id: id }
          : type === "uploaded" ? { source: "uploaded", set_id: id }
          : { source: "doc_generated", version_id: id };
      });
      let compositionId;
      if (items.length === 1 && items[0].source === "composition") {
        compositionId = items[0].composition_id;
      } else {
        const c = await apiPostEV(`/api/compositions`, { name: name || ("合并评测集-" + sel.length + "源"), items, created_by: "web" });
        compositionId = c.composition_id;
      }
      const run = await apiPostEV(`/api/evaluation-runs`, {
        composition_id: compositionId,
        name: name || null,
        adapter,
        adapter_config: cfg,
      });
      close();
      toast("已发起异步评测 #" + run.run_id + "，后台跑批中");
      window.__evView = "detail";
      window.__evOpenId = run.run_id;
      renderEvaluation();
    } catch (e) {
      toast("发起失败：" + e.message);
    }
  };
}

// ---------- 事件委托 ----------
document.addEventListener("click", e => {
  const seg = e.target.closest("#evViewSeg .seg button");
  if (seg) { window.__evView = seg.dataset.ev; if (seg.dataset.ev !== "detail") window.__evOpenId = null; renderEvaluation(); return; }
  const open = e.target.closest(".ev-open");
  if (open) { evOpenDetail(Number(open.dataset.run)); return; }
  if (e.target.closest("#evNewBtn")) { evStartRun(); return; }
});
