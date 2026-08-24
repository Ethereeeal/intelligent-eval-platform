/* ============ 评测集库（生成库 / 上传库 / 公共库 / 自定义评测集库） ============ */
/* 四个视图：
   - generate：生成库（原按文档问答库，renderLib("qa")）
   - uploaded：用户外部上传的评测集（默认全选）
   - public：平台预置公共库，按 6 个维度让用户填抽取数量（后端后接，当前占位）
   - custom：从 生成库(全选)+上传库(全选)+公共库(按数量抽样) 合并为自定义评测集库 */

const apiPostES = async (path, body) => {
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

// 公共库 6 维度（文件 → 维度名 + 占位可用量；后端接入后改为真实可用量）
const ES_PUBLIC_DIMS = [
  { key: "base", file: "模型基础能力-5000.json", name: "模型基础能力", total: 5000 },
  { key: "safety", file: "金融安全与价值对齐-2514.json", name: "金融安全与价值对齐", total: 2514 },
  { key: "risk", file: "金融风险控制-1000.json", name: "金融风险控制", total: 1000 },
  { key: "cog", file: "金融专业认知能力-3340.json", name: "金融专业认知能力", total: 3340 },
  { key: "biz", file: "业务拓展能力-12000.json", name: "业务拓展能力", total: 12000 },
  { key: "hard", file: "金融难题-3000.json", name: "金融难题", total: 3000 },
];

function esSetRow(set, kind) {
  const meta = [];
  if (set.version) meta.push("v" + set.version);
  if (set.total_cases != null) meta.push(set.total_cases + " 题");
  if (set.dimensions && set.dimensions.length) meta.push("维度:" + set.dimensions.join("/"));
  const q = (set.quality_snapshot && (set.quality_snapshot.pass_rate != null))
    ? `<span class="es-tag ok">质检通过 ${Math.round(set.quality_snapshot.pass_rate * 100)}%</span>` : "";
  return `<div class="list-row">
    <span class="st" style="--c:${kind === "upload" ? "#1B6CA8" : "#1B8A5A"}"></span>
    <div class="lr-tx">
      <div class="lr-q">${set.name || ("#" + set.set_id)}</div>
      <div class="lr-m">${meta.join(" · ") || "—"}</div>
    </div>
    ${q}
    <button class="btn ghost es-pick" data-kind="${kind}" data-id="${set.set_id}"><i data-lucide="arrow-up-right"></i>用于评测</button>
  </div>`;
}

async function renderEvalSetLibrary() {
  if (window.__evalSetReturn === "evaluation") {
    await esCreateComposition();
    return;
  }
  const gen = $("#esMain [data-sub='gen']");
  const show = $("#esMain [data-sub='show']");
  if (gen) gen.hidden = true;
  if (show) show.hidden = false;
  $$("#esSubNav .tree-row").forEach(row => row.classList.toggle("active", row.dataset.sub === "show"));

  // 进入「评测集展示」时按左侧下拉目录选中库加载
  const view = window.__esView || "generate";
  $$("#esSubNav .tree-row[data-es]").forEach(row => row.classList.toggle("active", row.dataset.es === view));
  $("#esGenerate").hidden = view !== "generate";
  $("#esUploaded").hidden = view !== "uploaded";
  $("#esPublic").hidden = view !== "public";
  $("#esCustom").hidden = view !== "custom";
  $("#esDoc").hidden = view !== "doclib";

  if (view === "generate") {
    // 生成库 = 原按文档问答库视图（质量与人工审核）
    if (!window.__esQaReady) { renderLib("qa"); window.__esQaReady = true; }
  }
  if (view === "uploaded") await esLoadUploaded();
  if (view === "public") await esLoadPublic();
  if (view === "doclib") renderLib("doc"); // 输入文档库界面（目录树+文档+解析+知识点+质量门禁+导出）
  if (view === "custom") await esLoadCustom();
  icons();
}

async function esLoadGenerate() {
  // 兼容保留：无冻结版本时的占位（当前生成库走 renderLib("qa")）
}

async function esCreateComposition() {
  const [versions, publicSets, uploadedSets] = await Promise.all([
    apiGet(`/api/versions`).catch(() => []),
    apiGet(`/api/public-sets`).catch(() => []),
    apiGet(`/api/eval-sets/uploaded`).catch(() => []),
  ]);
  const sources = [
    ...(versions || []).filter(v => v.status === "frozen").map(v => ({ value: `doc:${v.version_id}`, name: `生成库：${v.name || ("版本 #" + v.version_id)}` })),
    ...(publicSets || []).map(s => ({ value: `public:${s.set_id}`, name: `公共库：${s.name || ("#" + s.set_id)}` })),
    ...(uploadedSets || []).map(s => ({ value: `uploaded:${s.set_id}`, name: `上传库：${s.name || ("#" + s.set_id)}` })),
  ];
  const mask = document.createElement("div");
  mask.className = "modal-mask";
  mask.innerHTML = `<div class="modal modal-wide"><div class="modal-head"><span>创建评测库版本</span><button class="modal-x">×</button></div><div class="modal-body"><label class="es-field">版本名称</label><input class="es-input" id="esCompName" placeholder="例如：客服智能体回归集 v1"/><label class="es-field">选择来源（可多选合并）</label><div class="ev-src-list">${sources.map(s => `<label class="ev-src-item"><input type="checkbox" value="${s.value}"/> ${s.name}</label>`).join("") || "暂无可用来源"}</div></div><div class="modal-foot"><button class="btn ghost modal-cancel">取消</button><button class="btn primary" id="esCompSave">保存为评测库版本</button></div></div>`;
  document.body.appendChild(mask);
  const close = () => { window.__evalSetReturn = null; mask.remove(); };
  mask.querySelector(".modal-x").onclick = close;
  mask.querySelector(".modal-cancel").onclick = close;
  mask.querySelector("#esCompSave").onclick = async () => {
    const name = mask.querySelector("#esCompName").value.trim();
    const picked = [...mask.querySelectorAll("input:checked")].map(x => x.value);
    if (!name || !picked.length) return toast("请填写名称并至少选择一个来源");
    const items = picked.map(value => {
      const [kind, id] = value.split(":");
      return kind === "doc" ? { source: "doc_generated", version_id: Number(id) } : { source: kind, set_id: Number(id) };
    });
    try {
      const result = await apiPostES(`/api/compositions`, { name, items, created_by: "web" });
      close();
      window.__evSelectedCompositionId = result.composition_id;
      goto("evaluation");
    } catch (e) {
      toast("创建失败：" + e.message);
    }
  };
}

async function esLoadUploaded() {
  const box = $("#esUploadedList");
  box.innerHTML = `<div class="es-gen-hint">加载中…</div>`;
  try {
    const sets = await apiGet(`/api/eval-sets/uploaded`).catch(() => []);
    if (!sets.length) {
      box.innerHTML = `<div class="es-gen-hint">暂无上传评测集。点击右上角「上传评测集」导入单轮/多轮评测集（CSV/JSON/XLSX）。</div>`;
      return;
    }
    box.innerHTML = sets.map(s => esSetRow(s, "upload")).join("");
  } catch (e) {
    box.innerHTML = `<div class="es-gen-hint">加载失败：${e.message}</div>`;
  }
}

async function esLoadPublic() {
  const box = $("#esPubDims");
  if (!box) return;
  // 6 维度填数量 UI（后端后接，可用量暂用占位 total）
  box.innerHTML = ES_PUBLIC_DIMS.map(d => `<div class="pub-dim-row">
    <div class="pdr-info">
      <div class="pdr-name">${d.name}</div>
      <div class="pdr-file">${d.file} · 可用 ${d.total} 题</div>
    </div>
    <div class="pdr-input">
      <input type="number" class="gen-input pub-dim-num" min="0" max="${d.total}" value="0" data-dim="${d.key}" data-total="${d.total}" placeholder="0" />
      <span class="pdr-unit">题</span>
    </div>
  </div>`).join("");
  box.addEventListener("input", e => {
    const inp = e.target.closest(".pub-dim-num");
    if (!inp) return;
    let v = parseInt(inp.value) || 0;
    if (v < 0) v = 0;
    if (v > Number(inp.dataset.total)) { v = Number(inp.dataset.total); inp.value = v; }
    ES_PUBLIC_DIMS.forEach(d => { if (d.key === inp.dataset.dim) d.picked = v; });
    esPubCount();
  });
  esPubCount();
}

function esPubCount() {
  const v = ES_PUBLIC_DIMS.reduce((s, d) => s + (d.picked || 0), 0);
  const el = $("#gcsPub");
  if (el) el.textContent = v > 0 ? `抽样 ${v} 题` : "未选";
}

async function esLoadCustom() {
  // 摘要：生成库 / 上传库 题量（默认全选）
  const genEl = $("#gcsGen"), upEl = $("#gcsUp");
  let genN = 0, upN = 0;
  try {
    const sets = await apiGet(`/api/eval-sets/uploaded`).catch(() => []);
    upN = (sets || []).reduce((s, x) => s + (x.total_cases || 0), 0);
  } catch (e) {}
  // 生成库题量：从 qa 视图聚合（质量与人工审核库内全部评测集）
  try {
    genN = (window.__qaTotalCases != null) ? window.__qaTotalCases : 0;
  } catch (e) {}
  if (genEl) genEl.textContent = genN > 0 ? `${genN} 题（全选）` : "—";
  if (upEl) upEl.textContent = upN > 0 ? `${upN} 题（全选）` : "—";
  esPubCount();
  const build = $("#gcBuildBtn");
  const result = $("#gcResult");
  if (build) build.onclick = async () => {
    const name = ($("#gcName").value || "").trim();
    if (!name) { toast("请填写自定义评测集库名称"); return; }
    const pubN = ES_PUBLIC_DIMS.reduce((s, d) => s + (d.picked || 0), 0);
    const useGen = $("#gcGenAll").checked, useUp = $("#gcUpAll").checked, usePub = $("#gcPubOn").checked;
    if (!useGen && !useUp && !(usePub && pubN > 0)) { toast("请至少选择一个来源"); return; }
    build.disabled = true; build.textContent = "生成中…";
    try {
      // 后端后接：真实合并三库抽样。当前前端演示，记录选择并展示合并摘要。
      const summary = {
        name,
        generate: useGen ? genN : 0,
        uploaded: useUp ? upN : 0,
        public: usePub ? pubN : 0,
        public_dims: ES_PUBLIC_DIMS.filter(d => d.picked > 0).map(d => ({ dim: d.name, n: d.picked })),
        created_at: new Date().toISOString(),
      };
      window.__customSets = window.__customSets || [];
      window.__customSets.push(summary);
      if (result) result.innerHTML = `<div class="list-row">
        <span class="st" style="--c:#7A4FB0"></span>
        <div class="lr-tx">
          <div class="lr-q">${summary.name}</div>
          <div class="lr-m">生成库 ${summary.generate} · 上传库 ${summary.uploaded} · 公共库 ${summary.public} 题${summary.public_dims.length ? " · " + summary.public_dims.map(d => d.dim + " " + d.n).join("/") : ""}</div>
        </div>
        <span class="es-tag ok">已生成</span>
      </div>` + (result.innerHTML || "");
      toast("自定义评测集库已生成：" + name);
      $("#gcName").value = "";
    } catch (e) {
      toast("生成失败：" + e.message);
    } finally {
      build.disabled = false;
      build.innerHTML = `<i data-lucide="box"></i>生成自定义评测集库`;
      icons();
    }
  };
}

// 上传评测集
async function esHandleUpload(files) {
  for (const f of files) {
    try {
      const text = await f.text();
      let cases = [];
      if (f.name.endsWith(".json")) {
        const j = JSON.parse(text);
        cases = Array.isArray(j) ? j : (j.cases || []);
      } else if (f.name.endsWith(".csv")) {
        cases = text.trim().split("\n").slice(1).map(line => {
          const [q, a] = line.split(",");
          return { q: (q || "").trim(), a: (a || "").trim() };
        }).filter(c => c.q);
      } else {
        toast("暂仅支持 .json / .csv 上传");
        continue;
      }
      await apiPostES(`/api/eval-sets/uploaded`, {
        name: f.name.replace(/\.[^.]+$/, ""),
        version: "v1",
        multi_turn: false,
        cases,
      });
      toast("上传成功：" + f.name);
    } catch (e) {
      toast("上传失败 " + f.name + "：" + e.message);
    }
  }
  await esLoadUploaded();
  icons();
}

// 「用于评测」→ 跳到评测运行页并预选该来源
function esPickForEval(kind, id) {
  const map = {
    upload: { source: "uploaded", set_id: Number(id) },
  };
  window.__evPreset = map[kind] || null;
  goto("evaluation");
}

// 事件绑定（在 07-init 统一委托，这里仅声明处理函数）
document.addEventListener("click", e => {
  const libraryRow = e.target.closest("#esSubNav .tree-row[data-es]");
  if (libraryRow) {
    window.__esSub = "show";
    window.__esView = libraryRow.dataset.es;
    renderEvalSetLibrary();
    return;
  }
  const subRow = e.target.closest("#esSubNav .tree-row");
  if (subRow) {
    window.__esSub = subRow.dataset.sub;
    if (window.__esSub === "gen") renderEvalSetGenerate();
    else renderEvalSetLibrary();
    return;
  }
  const genBtn = e.target.closest("#esGenBtn");
  if (genBtn) { window.__esSub = "gen"; renderEvalSetGenerate(); return; }
  const pick = e.target.closest(".es-pick");
  if (pick) { esPickForEval(pick.dataset.kind, pick.dataset.id); return; }
  if (e.target.closest("#esUploadBtn")) { $("#esUploadInput").click(); return; }
});
document.addEventListener("change", e => {
  if (e.target.id === "esUploadInput" && e.target.files.length) {
    esHandleUpload([...e.target.files]);
    e.target.value = "";
  }
});
