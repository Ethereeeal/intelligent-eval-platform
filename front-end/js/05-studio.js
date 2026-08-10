  /* ---------------- 问答对生成（选择文件类型 / 配置 / 监控） ---------------- */
  function renderSrcList() {
    renderSrcTree();
  }

  /* 运行监测：演示环境无后端执行，仅展示已选文件并提供真实「导出已有问答对」下载 */
  function renderMonitor() {
    const el = $("#monitorList"); if (!el) return;
    const srcIds = state.studioSrc || [];
    if (!srcIds.length) {
      el.innerHTML = emptyState("尚未选择文件", "在左侧「选择文件类型」下勾选源文件后，点击「开始生成」即可在此导出现有问答对。");
      return;
    }
    const typeLabel = { doc: "待生成问答文件", qa: "仅泛化" }[state.studioType];
    el.innerHTML = srcIds.map(id => {
      const d = DOCS[id]; if (!d) return "";
      const tag = state.studioType === "doc"
        ? `难度${state.studioOpts.difficulties.join("/") || "未选"}${state.studioOpts.flatOutput ? "·扁平" : "·层级"}`
        : `×${state.studioOpts.generalizeCount}`;
      const qaN = (d.qa || []).length;
      return `<div class="monitor-row">
        <span class="mr-name">${d.name} · ${typeLabel} · ${tag}</span>
        <span class="mr-meta">已有问答对 ${qaN} 条</span>
        <span class="mr-pct"><button class="btn ghost sm mr-dl-btn" data-doc="${id}"><i data-lucide="download"></i>导出问答对</button></span>
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

    function renderNode(node, depth) {
      const hasChildren = node.children && node.children.length > 0;
      const docIds = hasChildren ? collectDocs(node) : (node.doc ? [node.doc] : []);
      const hasDocs = docIds.length > 0;
      const allSel = hasDocs && docIds.every(id => sel.has(id));
      const partSel = hasDocs && !allSel && docIds.some(id => sel.has(id));
      const icon = hasChildren ? "folder" : "file-text";

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
      html += `<span class="si-name">${node.name}</span>`;
      if (docIds.length) html += `<span class="si-meta">${docIds.length} 个</span>`;
      html += `</div>`;

      if (hasChildren && !collapsed[node.name]) {
        node.children.forEach(c => { html += renderNode(c, depth + 1); });
      }
      return html;
    }

    const wantPurpose = state.studioType === "qa" ? "gen" : "basic";
    const groups = TREE.children.filter(c => c.purpose === wantPurpose);
    $("#srcList").innerHTML = groups.length
      ? groups.map(c => `<div class="src-group">${renderNode(c, 0)}</div>`).join("")
      : emptyState("该类型下暂无语料", "当前语料库中没有「" + (state.studioType === "qa" ? "仅泛化" : "基础问题") + "输入文档」。");
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

  /* 渲染选项区：待生成问答文件 → 问答对生成（跨块+跨文档+难度多选+解释）；待泛化文件 → 问题泛化（数量+保留原始） */
  function renderStudioOpts() {
    const el = $("#studioOpts");
    if (!el) return;
    const o = state.studioOpts;
    let html = "";
    if (state.studioType === "doc") {
      html += `<div class="studio-subtitle">问答对生成</div>`;
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

