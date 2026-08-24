/* ============ 评测集库（生成 + 上传 + 公共库） ============ */
/* 三个视图：
   - generate：从文档生成评测集（已冻结版本 doc_generated 来源）
   - uploaded：用户外部上传的评测集
   - public：平台预置公共库，内部按名称/维度区分为「金融通用」与「风险合规」两块
   公共库分类为前端展示层处理：name/dimensions 含「金融/通用」归金融通用，
   含「合规/风险/监管」归风险合规，其余归入金融通用兜底。 */

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

function esIsFinance(set) {
  const blob = ((set.name || "") + " " + JSON.stringify(set.dimensions || [])).toLowerCase();
  if (/合规|风险|监管|合规风险/.test(blob)) return false;
  return true; // 金融通用 或 未明确标注的兜底
}

function esSetRow(set, kind) {
  const meta = [];
  if (set.version) meta.push("v" + set.version);
  if (set.total_cases != null) meta.push(set.total_cases + " 题");
  if (set.dimensions && set.dimensions.length) meta.push("维度:" + set.dimensions.join("/"));
  const q = (set.quality_snapshot && (set.quality_snapshot.pass_rate != null))
    ? `<span class="es-tag ok">质检通过 ${Math.round(set.quality_snapshot.pass_rate * 100)}%</span>` : "";
  return `<div class="list-row">
    <span class="st" style="--c:${kind === "risk" ? "#C0392B" : "#1B6CA8"}"></span>
    <div class="lr-tx">
      <div class="lr-q">${set.name || ("#" + set.set_id)}</div>
      <div class="lr-m">${meta.join(" · ") || "—"}</div>
    </div>
    ${q}
    <button class="btn ghost es-pick" data-kind="${kind}" data-id="${set.set_id}"><i data-lucide="arrow-up-right"></i>用于评测</button>
  </div>`;
}

async function renderEvalSet() {
  $$("#esViewSeg .seg button").forEach(b => b.classList.toggle("on", b.dataset.es === (window.__esView || "generate")));
  const view = window.__esView || "generate";
  $("#esGenerate").hidden = view !== "generate";
  $("#esUploaded").hidden = view !== "uploaded";
  $("#esPublic").hidden = view !== "public";
  $("#esEvaluation").hidden = view !== "evaluation";

  if (view === "generate") await esLoadGenerate();
  if (view === "uploaded") await esLoadUploaded();
  if (view === "public") await esLoadPublic();
  if (view === "evaluation") await esLoadEvaluationLibrary();
  icons();
}

async function esLoadGenerate() {
  const box = $("#esGenVersions");
  box.innerHTML = `<div class="es-gen-hint">加载中…</div>`;
  try {
    const versions = await apiGet(`/api/versions`).catch(() => []);
    const frozen = (versions || []).filter(v => v.status === "frozen");
    if (!frozen.length) {
      box.innerHTML = `<div class="es-gen-hint">暂无已冻结版本。请先在「评测集生成」完成任务，并在「输出评测集库」冻结版本。</div>`;
      return;
    }
    box.innerHTML = frozen.map(v => `<div class="list-row">
      <span class="st" style="--c:#124571"></span>
      <div class="lr-tx">
        <div class="lr-q">${v.name || ("版本 #" + v.version_id)}</div>
        <div class="lr-m">版本 #${v.version_id} · ${v.case_count || 0} 题 · 冻结 ${v.frozen_at ? v.frozen_at.slice(0, 10) : ""}</div>
      </div>
      <button class="btn ghost es-pick" data-kind="doc" data-id="${v.version_id}"><i data-lucide="arrow-up-right"></i>用于评测</button>
    </div>`).join("");
  } catch (e) {
    box.innerHTML = `<div class="es-gen-hint">加载失败：${e.message}</div>`;
  }
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
  const fin = $("#esPubFinance"), risk = $("#esPubRisk");
  fin.innerHTML = risk.innerHTML = `<div class="es-gen-hint">加载中…</div>`;
  try {
    const sets = await apiGet(`/api/public-sets`).catch(() => []);
    const finance = sets.filter(esIsFinance);
    const riskSets = sets.filter(s => !esIsFinance(s));
    fin.innerHTML = finance.length
      ? finance.map(s => esSetRow(s, "finance")).join("")
      : `<div class="es-gen-hint">暂无金融通用知识库条目。</div>`;
    risk.innerHTML = riskSets.length
      ? riskSets.map(s => esSetRow(s, "risk")).join("")
      : `<div class="es-gen-hint">暂无风险合规知识库条目。</div>`;
  } catch (e) {
    fin.innerHTML = risk.innerHTML = `<div class="es-gen-hint">加载失败：${e.message}</div>`;
  }
}

async function esLoadEvaluationLibrary() {
  const box = $("#esCompositionList");
  box.innerHTML = `<div class="es-gen-hint">加载中…</div>`;
  const items = await apiGet(`/api/compositions`).catch(() => []);
  box.innerHTML = items.length ? items.map(c => `<div class="list-row"><span class="st" style="--c:#8C7CF0"></span><div class="lr-tx"><div class="lr-q">${c.name}</div><div class="lr-m">评测库版本 #${c.composition_id} · ${Array.isArray(c.items) ? c.items.length : 0} 个来源</div></div><button class="btn ghost es-use-composition" data-id="${c.composition_id}">用于评测</button></div>`).join("") : `<div class="es-gen-hint">暂无正式评测集版本。请创建或合并来源评测集。</div>`;
}

async function esCreateComposition() {
  const [versions, publicSets, uploadedSets] = await Promise.all([apiGet(`/api/versions`).catch(() => []), apiGet(`/api/public-sets`).catch(() => []), apiGet(`/api/eval-sets/uploaded`).catch(() => [])]);
  const source = [
    ...(versions || []).filter(v => v.status === "frozen").map(v => ({ value: `doc:${v.version_id}`, name: `生成库：${v.name || ("版本 #" + v.version_id)}` })),
    ...(publicSets || []).map(s => ({ value: `public:${s.set_id}`, name: `公共库：${s.name || ("#" + s.set_id)}` })),
    ...(uploadedSets || []).map(s => ({ value: `uploaded:${s.set_id}`, name: `上传库：${s.name || ("#" + s.set_id)}` })),
  ];
  const mask = document.createElement("div"); mask.className = "modal-mask";
  mask.innerHTML = `<div class="modal modal-wide"><div class="modal-head"><span>创建评测库版本</span><button class="modal-x">×</button></div><div class="modal-body"><label class="es-field">版本名称</label><input class="es-input" id="esCompName" placeholder="例如：客服智能体回归集 v1"/><label class="es-field">选择来源（可多选合并）</label><div class="ev-src-list">${source.map(s => `<label class="ev-src-item"><input type="checkbox" value="${s.value}"/> ${s.name}</label>`).join("") || "暂无可用来源"}</div></div><div class="modal-foot"><button class="btn ghost modal-cancel">取消</button><button class="btn primary" id="esCompSave">保存为评测库版本</button></div></div>`;
  document.body.appendChild(mask); const close = () => mask.remove(); mask.querySelector(".modal-x").onclick = close; mask.querySelector(".modal-cancel").onclick = close;
  mask.querySelector("#esCompSave").onclick = async () => { const name = mask.querySelector("#esCompName").value.trim(); const picked = [...mask.querySelectorAll("input:checked")].map(x => x.value); if (!name || !picked.length) return toast("请填写名称并至少选择一个来源"); const items = picked.map(v => { const [kind, id] = v.split(":"); return kind === "doc" ? { source: "doc_generated", version_id: Number(id) } : { source: kind, set_id: Number(id) }; }); try { const result = await apiPostES(`/api/compositions`, { name, items, created_by: "web" }); close(); if (window.__evalSetReturn === "evaluation") { window.__evalSetReturn = null; window.__evSelectedCompositionId = result.composition_id; goto("evaluation"); } else esLoadEvaluationLibrary(); } catch (e) { toast("创建失败：" + e.message); } };
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
    doc: { source: "doc_generated", version_id: Number(id) },
    uploaded: { source: "uploaded", set_id: Number(id) },
    finance: { source: "public", set_id: Number(id) },
    risk: { source: "public", set_id: Number(id) },
    upload: { source: "uploaded", set_id: Number(id) },
  };
  window.__evPreset = map[kind] || null;
  goto("evaluation");
}

// 事件绑定（在 07-init 统一委托，这里仅声明处理函数）
document.addEventListener("click", e => {
  const seg = e.target.closest("#esViewSeg .seg button");
  if (seg) { window.__esView = seg.dataset.es; renderEvalSet(); return; }
  const pick = e.target.closest(".es-pick");
  if (pick) { esPickForEval(pick.dataset.kind, pick.dataset.id); return; }
  if (e.target.closest("#esUploadBtn")) { $("#esUploadInput").click(); return; }
  if (e.target.closest("#esComposeBtn")) { esCreateComposition(); return; }
  const composition = e.target.closest(".es-use-composition");
  if (composition) { if (window.__evalSetReturn === "evaluation") { window.__evalSetReturn = null; window.__evSelectedCompositionId = Number(composition.dataset.id); goto("evaluation"); } else { window.__evSelectedCompositionId = Number(composition.dataset.id); goto("evaluation"); } return; }
});
document.addEventListener("change", e => {
  if (e.target.id === "esUploadInput" && e.target.files.length) {
    esHandleUpload([...e.target.files]);
    e.target.value = "";
  }
});
