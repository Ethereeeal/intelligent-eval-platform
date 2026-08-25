  /* ---------------- 评测集生成（选择文件类型 / 配置 / 监控） ---------------- */
  function renderEvalSetGenerate() {
    const gen = $("#esMain [data-sub='gen']");
    const show = $("#esMain [data-sub='show']");
    if (gen) gen.hidden = false;
    if (show) show.hidden = true;
    $$("#esSubNav .tree-row").forEach(row => row.classList.toggle("active", row.dataset.sub === "gen"));
    renderSrcList();
    icons();
  }

  function renderSrcList() {
    renderSrcTree();
  }

  /* 生成进度条：studioRun 期间轮询后端进度并渲染到「运行监测」顶部 */
  function renderGenProgress(d, p) {
    const box = $("#genProgress"); if (!box) return;
    const total = p && p.total ? p.total : (d.kp || []).length;
    const done = p && p.done ? p.done : 0;
    const running = p ? p.running : true;
    const pct = total ? Math.min(100, Math.round(done / total * 100)) : 0;
    box.hidden = false;
    box.innerHTML = `
      <div class="gen-prog-head">
        <span class="gp-name">${d.name}</span>
        <span class="gp-meta">${running ? "生成中…" : "完成"} · ${done}/${total} 知识点</span>
        <span class="gp-pct">${pct}%</span>
      </div>
      <div class="gen-prog-bar"><span style="width:${pct}%"></span></div>`;
  }
  function hideGenProgress() {
    const box = $("#genProgress"); if (box) box.hidden = true;
  }
  function setGenProgressPhase(d, text) {
    const box = $("#genProgress"); if (!box || box.hidden) return;
    const head = box.querySelector(".gen-prog-head");
    if (head) {
      const meta = head.querySelector(".gp-meta");
      if (meta) meta.textContent = text;
    }
  }

  /* 运行监测：演示环境无后端执行，仅展示已选文件并提供真实「导出已有评测集」下载 */
  function renderMonitor() {
    const el = $("#monitorList"); if (!el) return;
    const srcIds = state.studioSrc || [];
    if (!srcIds.length) {
      el.innerHTML = emptyState("尚未选择文件", "在左侧「选择文件类型」下勾选源文件后，点击「开始生成」即可在此导出现有评测集。");
      return;
    }
    const typeLabel = { doc: "待生成问答文件", qa: "仅泛化" }[state.studioType];
    el.innerHTML = srcIds.map(id => {
      const d = DOCS[id]; if (!d) return "";
      const tag = state.studioType === "doc"
        ? `难度${state.studioOpts.difficulties.join("/") || "未选"}${state.studioOpts.flatOutput ? "·扁平" : "·层级"}`
        : `×${state.studioOpts.generalizeCount}`;
      const qaN = (d.qa || []).length;
      const eiuN = (d.kp || []).length;
      const metaBits = [];
      if (eiuN > 0) metaBits.push(`${eiuN} 知识点`); else if (d.status) metaBits.push(d.status);
      metaBits.push(`已有评测集 ${qaN} 条`);
      if (d.size) metaBits.push(d.size);
      return `<div class="monitor-row">
        <span class="mr-name">${d.name} · ${typeLabel} · ${tag}</span>
        <span class="mr-meta">${metaBits.join(" · ")}</span>
        <span class="mr-pct"><button class="btn ghost sm mr-dl-btn" data-doc="${id}"><i data-lucide="download"></i>导出评测集</button></span>
      </div>`;
    }).join("");
    icons();
    $$("#monitorList .mr-dl-btn").forEach(b => { b.onclick = () => exportQaSet(b.dataset.doc); });
  }

  function renderSrcTree() {
    const sel = new Set(state.studioSrc);
    state.srcCollapsed = state.srcCollapsed || {};
    const collapsed = state.srcCollapsed;

    function collectDocs(node) {
      return (node.children || []).flatMap(c => c.doc ? [c.doc] : collectDocs(c));
    }

    // 节点统计信息：文件夹聚合全部后代文档；文档取自身 EIU / 评测集 / 大小 / 类型
    function nodeStats(docIds) {
      let eiuN = 0, qaN = 0;
      docIds.forEach(id => {
        const d = DOCS[id]; if (!d) return;
        eiuN += (d.kp || []).length;
        qaN += (d.qa || []).length;
      });
      return { eiuN, qaN };
    }
    function renderNode(node, depth) {
      const isFolder = Array.isArray(node.children);
      const hasChildren = isFolder && node.children.length > 0;
      const docIds = hasChildren ? collectDocs(node) : (node.doc ? [node.doc] : []);
      const hasDocs = docIds.length > 0;
      const allSel = hasDocs && docIds.every(id => sel.has(id));
      const partSel = hasDocs && !allSel && docIds.some(id => sel.has(id));
      const icon = isFolder ? "folder" : "file-text";

      // 第一行右侧 + 第二行小字
      let line1Meta = "", line2 = "";
      if (isFolder) {
        if (hasDocs) {
          const s = nodeStats(docIds);
          line1Meta = `${docIds.length} 篇`;
          line2 = `${s.eiuN} 知识点 · ${s.qaN} 评测集`;
        } else {
          line2 = "空文件夹";
        }
      } else {
        const d = DOCS[node.doc] || {};
        const s = nodeStats(docIds);
        line1Meta = s.eiuN > 0 ? `${s.eiuN} 知识点` : (d.status && d.status !== "已解析" ? d.status : "暂无知识点");
        const bits = [];
        if (s.qaN > 0) bits.push(`${s.qaN} 评测集`);
        if (d.size) bits.push(d.size);
        if (d.type) bits.push(d.type);
        line2 = bits.join(" · ");
      }

      let html = `<div class="src-tn${depth === 0 ? ' src-tn-root' : ''}" style="padding-left:${depth*18+4}px">`;
      html += hasChildren
        ? `<span class="src-tn-arr" data-folder="${node.name}">${collapsed[node.name] ? '▸' : '▾'}</span>`
        : `<span class="src-tn-arr noop"></span>`;
      html += hasDocs
        ? `<label class="src-tn-chk ${partSel ? 'part' : ''}">
            <input type="checkbox" ${allSel ? 'checked' : ''} data-docs="${docIds.join(',')}">
            <span class="src-tn-ckmark"></span></label>`
        : `<span class="src-tn-arr noop"></span>`;
      html += `<i data-lucide="${icon}" class="src-tn-ic"></i>`;
      html += `<div class="si-body">`;
      html += `<div class="si-line1"><span class="si-name">${node.name}</span>${line1Meta ? `<span class="si-meta">${line1Meta}</span>` : ""}</div>`;
      if (line2) html += `<div class="si-sub">${line2}</div>`;
      html += `</div></div>`;

      if (hasChildren && !collapsed[node.name]) {
        node.children.forEach(c => { html += renderNode(c, depth + 1); });
      }
      return html;
    }

    // 统一文档库：文件树展示全部文档，由用户自行勾选；是否泛化由下方模式与选项决定
    const hasAnyDoc = collectDocs(TREE).length > 0;
    $("#srcList").innerHTML = hasAnyDoc
      ? `<div class="src-group">${renderNode(TREE, 0)}</div>`
      : emptyState("文档库为空", "当前文档库中没有输入文档，请先到「输入文档库」上传。");
    icons();

    $$("#srcList .src-tn-arr[data-folder]").forEach(arr => {
      arr.onclick = () => { collapsed[arr.dataset.folder] = !collapsed[arr.dataset.folder]; renderSrcTree(); };
    });
      $$("#srcList .src-tn-chk input[type=checkbox]").forEach(cb => {
        cb.onclick = (e) => {
          e.stopPropagation();
          const ids = cb.dataset.docs.split(",").filter(Boolean);
          if (cb.checked) { ids.forEach(id => sel.add(id)); }
          else { ids.forEach(id => sel.delete(id)); }
          state.studioSrc = [...sel].sort();
          renderSrcTree();
        };
      });
      renderMonitor();
  }

  /* 渲染选项区：待生成问答文件 → 评测集生成（跨块+跨文档+难度多选+解释）；待泛化文件 → 问题泛化（数量+保留原始） */
  function renderStudioOpts() {
    const el = $("#studioOpts");
    if (!el) return;
    const o = state.studioOpts;
    let html = "";
    if (state.studioType === "doc") {
      html += `<div class="studio-subtitle">评测集生成</div>`;
      html += `<div class="gen-row out-mode-row"><span class="gen-label">输出结构</span>
        <div class="seg out-mode-seg" id="outModeSeg">
          <button class="${o.flatOutput ? "" : "on"}" data-mode="tree">保留目录层级</button>
          <button class="${o.flatOutput ? "on" : ""}" data-mode="flat">扁平化输出</button>
        </div></div>`;
      html += `<div class="gen-row out-mode-row" style="margin-top:14px"><span class="gen-label">问题采样策略</span>
        <label class="opt"><input type="checkbox" id="optCrossBlock" ${o.crossBlock ? "checked" : ""} /> <span>跨块问题组合</span></label>
        <label class="opt"><input type="checkbox" id="optCrossDoc" ${o.crossDoc ? "checked" : ""} /> <span>跨文档生成</span></label>
      </div>`;
      html += `<div class="diff-row"><span class="diff-label">难度</span>`;
      ["简单", "中等", "难"].forEach(d => {
        html += `<label class="diff-chk"><input type="checkbox" value="${d}" ${o.difficulties.includes(d) ? "checked" : ""} /> <span>${d}</span></label>`;
      });
      html += `</div>`;
      html += `<div class="diff-desc">`;
      html += `<p><b>简单</b>：直接查找 / 原文匹配，单句范围内可回答</p>`;
      html += `<p><b>中等</b>：需要归纳概括或跨句推理，涉及一点计算或比较</p>`;
      html += `<p><b>难</b>：需要多步推理、跨段跨文档综合，或隐含条件推导</p>`;
      html += `</div>`;
    } else {
      html += `<div class="studio-subtitle">问题泛化</div>`;
      html += `<div class="gen-row"><span class="gen-label">每个原始问题生成</span><input type="number" class="gen-input" id="genCount" value="${o.generalizeCount}" min="1" max="20" /> <span class="gen-label">个泛化问题</span></div>`;
      html += `<label class="opt"><input type="checkbox" id="optKeepOrig" ${o.keepOriginal ? "checked" : ""} /> <span>同时保留原始问题</span></label>`;
    }
    el.innerHTML = html;
    icons();
    if (state.studioType === "doc") {
      const cbCB = $("#optCrossBlock"); if (cbCB) cbCB.onchange = () => { o.crossBlock = cbCB.checked; };
      const cbCD = $("#optCrossDoc"); if (cbCD) cbCD.onchange = () => { o.crossDoc = cbCD.checked; };
      const omSeg = $("#outModeSeg"); if (omSeg) omSeg.addEventListener("click", e => {
        const b = e.target.closest("button[data-mode]"); if (!b) return;
        omSeg.querySelectorAll("button").forEach(x => x.classList.toggle("on", x === b));
        o.flatOutput = b.dataset.mode === "flat";
      });
      $$("#studioOpts .diff-chk input[type=checkbox]").forEach(cb => {
        cb.onchange = () => {
          o.difficulties = [...$$("#studioOpts .diff-chk input[type=checkbox]:checked")].map(c => c.value);
        };
      });
    } else {
      const gc = $("#genCount"); if (gc) gc.onchange = () => { o.generalizeCount = parseInt(gc.value) || 3; };
      const ko = $("#optKeepOrig"); if (ko) ko.onchange = () => { o.keepOriginal = ko.checked; };
    }
  }

  function esGeneratorDifficulty(value) {
    return ({ L1: "简单", L2: "中等", L3: "难" })[value] || value || "中等";
  }

  function esGeneratorCopyCase(item, fallbackSource, index) {
    return {
      id: `custom-${Date.now()}-${index}-${Math.random().toString(36).slice(2, 7)}`,
      q: item.q || item.question || "",
      a: item.a || item.answer || item.gold_answer || "",
      evidence: Array.isArray(item.evidence) ? item.evidence.map(x => x.original_text || x.text || "").filter(Boolean).join("；") : (item.evidence || ""),
      src: item.src || item.source || item.document_name || fallbackSource,
      diff: esGeneratorDifficulty(item.diff || item.difficulty),
    };
  }

  function esGeneratorFolderTree(items, attribute) {
    const root = { folders: new Map(), items: [] };
    items.forEach(item => {
      const parts = String(item.folder_path || "").split("/").map(part => part.trim()).filter(Boolean);
      let node = root;
      parts.forEach(part => {
        if (!node.folders.has(part)) node.folders.set(part, { folders: new Map(), items: [] });
        node = node.folders.get(part);
      });
      node.items.push(item);
    });
    const render = node => {
      const files = node.items.map(item => `<label class="ev-src-item"><input type="checkbox" ${attribute}="${escapeHTML(String(item.id))}"/>${escapeHTML(item.name)}<span class="es-generator-meta">${escapeHTML(item.meta)}</span></label>`).join("");
      const folders = [...node.folders.entries()].map(([name, child]) => `<details class="es-generator-folder" open><summary><i data-lucide="folder"></i>${escapeHTML(name)}</summary>${render(child)}</details>`).join("");
      return folders + files;
    };
    return render(root) || "暂无文件";
  }

  async function openEvalSetGeneratorModal() {
    const [remoteUploads] = await Promise.all([apiGet(`/api/eval-sets/uploaded`).catch(() => [])]);
    const uploadedSets = remoteUploads.length ? remoteUploads : ES_UPLOADED_SAMPLES;
    const docs = Object.entries(DOCS).map(([id, doc]) => ({ id, name: doc.name, meta: `${(doc.kp || []).length} 知识点 · ${(doc.qa || []).length} 题`, folder_path: doc.folderPath || "" }));
    const mask = document.createElement("div");
    mask.className = "modal-mask";
    mask.innerHTML = `<div class="modal modal-wide es-generator-modal">
      <div class="modal-head"><span>生成评测集</span><button class="modal-x" type="button">×</button></div>
      <div class="modal-body es-generator-body">
        <label class="es-field">评测集名称</label><input class="es-input" id="esGeneratorName" value="组合评测集 ${new Date().toLocaleDateString("zh-CN")}" />
        <section class="es-generator-section"><div class="es-generator-title">文档库</div><p class="es-generator-hint">从文档库中的任意文档多选，保留原有文件夹层级；所选文档会按已有生成能力补齐评测集。</p><div class="es-generator-list">${esGeneratorFolderTree(docs, "data-es-generator-doc")}</div></section>
        <section class="es-generator-section"><div class="es-generator-title">生成策略</div><div class="es-generator-policy-grid"><div class="es-generator-policy"><span class="es-generator-policy-label">采样策略</span><div class="es-generator-policy-controls"><label class="opt"><input type="checkbox" id="esGeneratorCrossBlock" checked/><span>跨块问题组合</span></label><label class="opt"><input type="checkbox" id="esGeneratorCrossDoc" checked/><span>跨文档生成</span></label></div></div><div class="es-generator-policy"><span class="es-generator-policy-label">难度</span><div class="es-generator-policy-controls">${["简单", "中等", "难"].map(level => `<label class="diff-chk"><input type="checkbox" value="${level}" data-es-generator-difficulty checked/><span>${level}</span></label>`).join("")}</div></div></div></section>
        <section class="es-generator-section"><div class="es-generator-title">上传库</div><p class="es-generator-hint">上传评测集按其文件夹层级展示。</p><div class="es-generator-list">${esGeneratorFolderTree(uploadedSets.map((set, index) => ({ id: index, name: set.name || `上传评测集 #${set.set_id}`, meta: `${set.total_cases || set.cases?.length || 0} 题`, folder_path: set.folder_path || "" })), "data-es-generator-upload")}</div></section>
        <section class="es-generator-section"><div class="es-generator-title">公共库</div><p class="es-generator-hint">可按六个维度分别填写纳入题量，填写 0 表示不纳入。</p><div class="es-public-quota">${ES_PUBLIC_DIMS.map(dim => `<label><span>${escapeHTML(dim.name)}</span><input class="gen-input" type="number" min="0" max="${dim.total}" value="0" data-es-generator-public="${escapeHTML(dim.key)}"/><em>/ ${dim.total} 题</em></label>`).join("")}</div></section>
      </div>
      <div class="modal-foot"><button class="btn ghost modal-cancel" type="button">取消</button><button class="btn primary" id="esGeneratorSubmit" type="button"><i data-lucide="sparkles"></i>生成并存入评测集库</button></div>
    </div>`;
    document.body.appendChild(mask);
    const close = () => mask.remove();
    mask.querySelector(".modal-x").onclick = close;
    mask.querySelector(".modal-cancel").onclick = close;
    mask.querySelector("#esGeneratorSubmit").onclick = async () => {
      const docIds = [...mask.querySelectorAll("[data-es-generator-doc]:checked")].map(input => input.dataset.esGeneratorDoc);
      const uploadIndexes = [...mask.querySelectorAll("[data-es-generator-upload]:checked")].map(input => Number(input.dataset.esGeneratorUpload));
      const publicQuota = Object.fromEntries([...mask.querySelectorAll("[data-es-generator-public]")].map(input => [input.dataset.esGeneratorPublic, Math.max(0, Math.min(Number(input.max), Number(input.value) || 0))]));
      const difficulties = [...mask.querySelectorAll("[data-es-generator-difficulty]:checked")].map(input => input.value);
      if (!docIds.length && !uploadIndexes.length && !Object.values(publicQuota).some(Boolean)) return toast("请至少选择文档、上传评测集或公共库题量", "warn");
      if (!difficulties.length) return toast("请至少选择一种难度", "warn");
      const submit = mask.querySelector("#esGeneratorSubmit");
      submit.disabled = true;
      submit.textContent = "生成中…";
      const failedDocs = [];
      for (const id of docIds) {
        const doc = DOCS[id];
        const documentId = Number(String(id).replace(/^doc/, ""));
        if (!doc || !Number.isFinite(documentId) || !(doc.kp || []).length) continue;
        try {
          const response = await fetch(API_BASE + `/api/cases/generate?document_id=${documentId}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ angles: ["primary"], include_variations: false, dry_run: false }) });
          if (!response.ok) throw new Error(String(response.status));
          const qualityResponse = await fetch(API_BASE + `/api/quality-check?document_id=${documentId}`, { method: "POST" });
          if (!qualityResponse.ok) throw new Error(`质量检查 ${qualityResponse.status}`);
        } catch (error) { failedDocs.push(doc.name); }
      }
      const name = mask.querySelector("#esGeneratorName").value.trim() || "未命名评测集";
      const uploadedSetIds = uploadIndexes.map(index => uploadedSets[index]?.set_id).filter(id => Number.isInteger(Number(id)));
      if (uploadIndexes.length !== uploadedSetIds.length) { submit.disabled = false; submit.textContent = "生成并存入评测集库"; return toast("上传库样例不能永久保存，请选择已实际上传的评测集", "warn"); }
      const generationConfig = { cross_block: mask.querySelector("#esGeneratorCrossBlock").checked, cross_document: mask.querySelector("#esGeneratorCrossDoc").checked, difficulties, output: "flat" };
      const payload = {
        name,
        created_by: "web",
        document_ids: docIds.map(id => Number(String(id).replace(/^doc/, ""))).filter(Number.isFinite),
        uploaded_set_ids: uploadedSetIds.map(Number),
        public_selections: ES_PUBLIC_DIMS.filter(dim => publicQuota[dim.key]).map(dim => ({ dimension: dim.key, count: publicQuota[dim.key] })),
        generation_config: generationConfig,
      };
      try {
        const response = await fetch(API_BASE + "/api/freeze", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
        if (!response.ok) { const body = await response.json().catch(() => ({})); throw new Error(body.detail || response.status); }
        close();
        window.__esView = "custom";
        await renderEvalSetLibrary();
        toast(failedDocs.length ? `已永久存入评测集库；${failedDocs.length} 个文档生成未完成` : "已永久存入评测集库");
      } catch (error) {
        submit.disabled = false;
        submit.innerHTML = `<i data-lucide="sparkles"></i>生成并存入评测集库`;
        icons();
        toast("持久化失败：" + error.message, "warn");
      }
    };
    icons();
  }
