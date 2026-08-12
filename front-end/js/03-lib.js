  /* ---------------- 库内容渲染 ---------------- */
  function emptyState(title, desc) {
    return `<div class="empty-state"><div class="es-ic"><i data-lucide="shield-question"></i></div>
      <div class="es-t">${title}</div><div class="es-d">${desc}</div></div>`;
  }

  // 在线查看：从后端拉取文档原文 blocks 并渲染到预览区
  async function openOnlineView(docId) {
    const d = DOCS[docId];
    const preview = $("#docContent .doc-preview");
    if (!preview) return;
    const docIdNum = Number(String(docId).replace(/^doc/, ""));
    preview.classList.remove("collapsed"); // 点击「在线查看」立即展开，再加载原文
    const arr = $("#docContent #ovToggle .t-arr"); if (arr) arr.textContent = "▾";
    preview.innerHTML = `<p class="muted">正在加载文档原文…</p>`;
      try {
        const blocks = await apiGet(`/api/documents/${docIdNum}/blocks`);
        const paras = (blocks || []).filter(b => b.block_type !== "title" && (b.block_text || "").trim());
        if (!paras.length) {
          preview.innerHTML = `<p class="muted">该文档暂无可展示的原文内容</p>`;
          return;
        }
        preview.innerHTML = paras.map(b => {
          const sec = b.section_path && b.section_path !== "未分类" ? `<span class="bk-sec">${escapeHTML(b.section_path)}</span>` : "";
          return `<div class="doc-block">${sec}<p>${escapeHTML(b.block_text).replace(/\n+/g, "<br>")}</p></div>`;
        }).join("");
        toast(`已加载《${d.name}》原文 ${paras.length} 段`);
      } catch (err) {
        preview.innerHTML = `<p class="muted">文档原文加载失败：${err.message}</p>`;
      }
  }

  function docContentHTML(docId) {
    const d = DOCS[docId];
    const isParsing = d.status.includes("解析中");
    const progressBar = isParsing ? `<div class="upload-prog-wrap mt"><div class="upload-prog-track"><div class="upload-prog-bar" style="width:${Math.round(d.parseProgress||0)}%"></div></div><span class="upload-prog-txt">知识点解析中 ${Math.round(d.parseProgress||0)}%</span></div>` : "";
    return `<div class="lib-head">
        <div class="lh-ic"><i data-lucide="file-text"></i></div>
        <div><div class="lh-title">${d.name}</div><div class="lh-sub">${d.type} · ${d.size} · ${d.status} · ${d.ver} · ${d.updated}</div></div>
        <div class="lib-actions"><button class="btn ghost sm" id="btnVersion"><i data-lucide="history"></i>版本</button><button class="btn ghost sm" id="dlEIUDoc"><i data-lucide="download"></i>导出知识点</button></div>
      </div>
      <div class="card card-pad">
        ${progressBar}
        <div class="sec-h sec-toggle" id="ovToggle"><span class="t-arr">▸</span>在线查看</div>
        <div class="doc-preview collapsed" id="docPreview">${d.preview.length ? d.preview.map(p => `<p>${p}</p>`).join("") : `<p class="muted">点击上方「在线查看」标题展开文档原文预览</p>`}</div>
        <div class="sec-h mt">版本历史</div>
        <div class="ver-list">${d.versions.map(v => `<div class="ver"><span class="ver-tag">${v.tag}</span><span>${v.note}</span><span class="mut">${v.time}</span></div>`).join("")}</div>
        <div class="sec-h mt kp-sec-h">知识点 · ${d.kp.length} 条<button class="btn ghost sm kp-export-btn" id="dlEIUKp"><i data-lucide="download"></i>导出</button><button class="btn ghost icon-only sm kp-zoom-btn" id="kpFullscreenBtn" title="放大查看"><i data-lucide="maximize"></i></button></div>
        ${d.kp && d.kp.length ? kpTableHTML(d.kp) : `<p class="muted mt">${isParsing ? "正在解析中..." : "未识别到可抽取知识点。"}</p>`}
      </div>`;
  }

  function folderDocGridHTML(node) {
    const docs = descendantDocs(node);
    return `<div class="lib-head"><div class="lh-ic"><i data-lucide="folder-open"></i></div>
        <div><div class="lh-title">${node.name}</div><div class="lh-sub">${docs.length} 个文档</div></div></div>
      <div class="doc-grid">${docs.map(id => {
        const d = DOCS[id];
        return `<div class="doc-card" data-doc="${id}">
          <div class="dc-top"><div class="dc-ic"><i data-lucide="file-text"></i></div>
            <div><div class="dc-name">${d.name}</div><div class="dc-meta">${d.type} · ${d.size} · <span style="color:var(--ok)">${d.status}</span></div></div></div>
          <div class="doc-preview kp-count">${kpCountHTML(d)}</div>
        </div>`;
      }).join("")}</div>`;
  }

  // 文档卡片底部：原空白 preview 区域改为展示「生成知识点数量」（纯文字）
  function kpCountHTML(d) {
    const kpN = (d.kp || []).length, qaN = (d.qa || []).length;
    const text = kpN > 0 ? `${kpN} 个知识点` : (qaN > 0 ? `${qaN} 个问答对` : "暂无知识点");
    return `<p class="kp-count-text">${text}</p>`;
  }

  // 知识点表格：标题行「知识点 / 推荐 / 类型 / 证据 / 来源文档」，无图标
  function kpTableHTML(all) {
    return `<div class="kp-table kp-table-filterable">
      <div class="kp-th">
        <span>知识点<span class="col-filter" data-filter="stmt"><i data-lucide="filter"></i></span><span class="kp-resize" data-resize="0"></span></span>
        <span>推荐<span class="col-filter" data-filter="prio"><i data-lucide="filter"></i></span><span class="kp-resize" data-resize="1"></span></span>
        <span>类型<span class="col-filter" data-filter="type"><i data-lucide="filter"></i></span><span class="kp-resize" data-resize="2"></span></span>
        <span>证据<span class="col-filter" data-filter="ev"><i data-lucide="filter"></i></span><span class="kp-resize" data-resize="3"></span></span>
        <span>来源文档<span class="col-filter" data-filter="src"><i data-lucide="filter"></i></span></span>
      </div>
      ${all.map((k, i) => `<div class="kp-tr">
        <span class="kp-td kp-td-stmt kp-c-stmt"><b>#${i + 1}</b> ${escapeHTML(k.stmt)}</span>
        <span class="kp-td kp-c-prio">${escapeHTML(k.prio)}</span>
        <span class="kp-td kp-c-type"><span class="pill br">${escapeHTML(k.type)}</span></span>
        <span class="kp-td kp-td-ev kp-c-ev">${escapeHTML(k.ev)}</span>
        <span class="kp-td kp-td-src kp-c-src">${escapeHTML(k.src)}</span>
      </div>`).join("")}
    </div>`;
  }

  function kpContentHTML(docId) {
    const d = DOCS[docId];
    if (!d.kp || d.kp.length === 0) {
      return `<div class="lib-head"><div class="lh-ic"><i data-lucide="file-x"></i></div>
        <div><div class="lh-title">${d.name}</div><div class="lh-sub">知识点</div></div></div>` +
        emptyState("该文档无知识点", "已执行拒答验证：所选文档无可提取知识点，未生成问答对（不单独成栏）。");
    }
    return `<div class="lib-head"><div class="lh-ic"><i data-lucide="list-checks"></i></div>
        <div><div class="lh-title">${d.name}</div><div class="lh-sub">知识点 · ${d.kp.length} 条</div></div>
        <div class="lib-actions"><button class="btn ghost sm" id="kpFullscreenBtn"><i data-lucide="maximize"></i>放大查看</button><button class="btn ghost sm" id="dlEIUKp"><i data-lucide="download"></i>导出知识点</button></div></div>
      <div class="card card-pad">
        ${kpTableHTML(d.kp)}
        <p class="muted mt">证据定位示例：${d.kp[0].ev}；来源文档：${d.kp[0].src}；置信度≥0.9 视为已覆盖。</p>
      </div>`;
  }

  function renderLibContent(mode, docId) {
    state.folderSel[mode] = null;
    if (mode === "doc") {
      // 文档库空（全部文档已删除）时展示空态，避免 d 为 undefined 报错
      if (!docId || !DOCS[docId]) {
        $("#docContent").innerHTML = emptyState("文档库为空", "上传文档后自动解析分块并抽取知识点，支持新建文件夹/子目录组织。");
        icons();
        return;
      }
      $("#docContent").innerHTML = docContentHTML(docId);
      const dl = $("#docContent #dlEIUDoc"); if (dl) dl.onclick = () => downloadEIU(docId);
      const kpDl = $("#docContent #dlEIUKp"); if (kpDl) kpDl.onclick = () => downloadEIU(docId);
      // 在线查看：标题栏箭头点击展开/收回（默认收起，向下箭头展开、向上箭头收回）
      const ovToggle = $("#docContent #ovToggle");
      if (ovToggle) ovToggle.onclick = () => {
        const prev = $("#docContent .doc-preview");
        const willExpand = prev.classList.contains("collapsed");
        const expanded = prev.classList.toggle("collapsed") === false;
        ovToggle.querySelector(".t-arr").textContent = expanded ? "▾" : "▸";
        if (willExpand) openOnlineView(docId); // 仅展开时按需从后端拉取原文
      };
      const ver = $("#docContent #btnVersion"); if (ver) ver.onclick = () => {
        const d = DOCS[docId];
        if (!d.versions || !d.versions.length) toast("演示环境：该文档暂无版本记录");
        else toast("版本：" + d.versions.map(v => v.tag).join(" / "));
      };
      const kpf = $("#docContent #kpFullscreenBtn"); if (kpf) kpf.onclick = () => openKpFullscreen(DOCS[docId].kp, DOCS[docId].name);
      bindKpColFilters($("#docContent"));
      bindKpColResize($("#docContent .kp-table"));
      setupPager($("#docContent"), "#docContent .kp-tr", 15, "kpPager", "kpPage");
      enableHScrollDrag($("#docContent .kp-table"));
    } else {
      // 查看具体文档时，左目录已无导航价值，自动收起使问答对内容占满浏览器宽度
      const qaSplit = $("#qaContent").closest(".lib-split");
      const qaTreeEl = qaSplit ? qaSplit.querySelector(".tree") : null;
      if (qaTreeEl) qaTreeEl.classList.add("collapsed");
      if (qaSplit) qaSplit.classList.add("tree-hidden");
      const rbEl = $(".tree-reopen"); if (rbEl) rbEl.classList.toggle("show", true);
      // 删除文档后选中可能失效：自动回退到第一个仍有问答对的文档，否则展示空态
      if (!docId || !DOCS[docId]) {
        const first = Object.keys(DOCS).find(id => (DOCS[id].qa || []).length);
        if (first) {
          state.sel.qa = first;
          const fRow = $(`#qaTree .tree-row[data-qa-id="${first}"]`);
          if (fRow) { $$("#qaTree .tree-row.active").forEach(x => x.classList.remove("active")); fRow.classList.add("active"); }
          renderLibContent("qa", first);
          return;
        }
        $("#qaContent").innerHTML = emptyState("问答对库为空", "上传文档并生成问答对后，可在此查看与管理。");
        icons();
        return;
      }
      const d = DOCS[docId];
      if (!d.qa || !d.qa.length) {
        $("#qaContent").innerHTML = qaHead(docId) + emptyState("该文档无问答对", "已执行拒答验证：所选文档无可提取知识点，未生成问答对（不单独成栏）。");
      } else {
        $("#qaContent").innerHTML = qaHead(docId) + qaBlockHTML(d.qa, "qaChart-" + docId);
        qaBind("qaChart-" + docId);
      }
    }
    icons();
  }

  function renderLib(mode) {
    const treeId = mode === "doc" ? "#docTree" : "#qaTree";
    if (mode === "qa") bindQaTree($(treeId));
    else bindTree($(treeId), mode);
    renderLibContent(mode, state.sel[mode]);
    // 打开「输出问答对库」栏目时，默认展开目录：renderLibContent 在查看具体集时会折叠目录，
    // 故在渲染内容之后再强制展开并取消隐藏，确保刚进入栏目时目录始终是展开态。
    if (mode === "qa") {
      const qaSplit = $(treeId) && $(treeId).closest(".lib-split");
      if (qaSplit) { qaSplit.classList.remove("tree-hidden"); qaSplit.querySelector(".tree").classList.remove("collapsed"); }
      const rb = $(".tree-reopen"); if (rb) rb.classList.remove("show");
      // 注：各节点的展开/折叠由 QA_COLLAPSED 记忆并在 qaTreeHTML 中渲染，
      // 此处只负责恢复整个目录面板的显示，不再强制展开所有节点。
    }
  }

  // 类型标签：gen=泛化问题 plain=基础问题
  function typeLabel(t) { return t === "gen" ? "泛化问题" : (t === "plain" ? "基础问题" : t); }

  // ============================================================
  // 输出问答对库目录树（后端驱动，真实持久化）
  // ------------------------------------------------------------
  // 结构与「输入文档库」完全同构：
  //   泛化问题 / 基础问题（两个系统根，不可重命名/删除）
  //     └─ 用户文件夹（来自 /api/folders，与输入库共享同一份持久化目录）
  //          └─ 问答对集（按其问答对上后端持久化的 folder_path 归位）
  // 交互也与输入库一致：chevron-down 箭头 + 可折叠（.tree-node/.tree-children.open/.collapsed）
  // ============================================================

  // 系统根定义：key 为前端 qa.type，purpose 为后端持久化字段
  const QA_ROOTS = [
    { key: "gen", name: "泛化问题", purpose: "gen" },
    { key: "plain", name: "基础问题", purpose: "basic" }
  ];

  // 折叠态记忆：key = `${rootKey}:${relPath}`，值为 true 表示已折叠。
  // 重渲染（新建/重命名/移动后）时保持用户的展开/折叠状态。
  if (!window.QA_COLLAPSED) window.QA_COLLAPSED = {};

  // 由后端 folder 扁平列表构建某个系统根下的目录树（每个根独立造节点，互不共享）
  function qaFolderTree() {
    const byParent = {};
    (QA_FOLDERS || []).forEach(f => {
      const k = (f.parent_id == null) ? "root" : f.parent_id;
      (byParent[k] = byParent[k] || []).push(f);
    });
    function make(parentKey) {
      return (byParent[parentKey] || []).map(f => ({
        name: f.name, folderId: f.folder_id, children: make(f.folder_id)
      }));
    }
    return make("root");
  }

  // 某系统根下的问答对集：按 purpose 过滤，返回 { relPath -> [docId] }
  function qaSetsByPath(rootKey) {
    const map = {};
    Object.keys(DOCS).forEach(id => {
      const rows = (DOCS[id].qa || []).filter(q => q.type === rootKey);
      if (!rows.length) return;
      const rel = (rows.find(r => r.folderPath) || {}).folderPath || DOCS[id].qaFolderPath || "";
      (map[rel] = map[rel] || []).push(id);
    });
    return map;
  }

  function qaTreeHTML() {
    let html = `<div class="tree-h up-title">问答对目录</div>`;
    html += `<div class="lib-hint"><i data-lucide="info"></i><div><b>问答对库</b>：目录与「输入文档库」同构，问答对集随源文档目录自动归位；可新建文件夹、移动、重命名，并支持按目录导出。</div></div>`;
    QA_ROOTS.forEach(root => {
      const folders = qaFolderTree();
      const setsByPath = qaSetsByPath(root.key);
      const total = Object.values(setsByPath).reduce((s, arr) => s + arr.length, 0);
      const collapsed = !!window.QA_COLLAPSED[`${root.key}:`];
      html += `<div class="tree-node">
        <div class="tree-row${collapsed ? " collapsed" : ""}" data-qa-folder="1" data-qa-root="1" data-root-key="${root.key}" data-path="" data-name="${root.name}">
          <i data-lucide="folder" class="tw-ic"></i><span class="tw-name">${root.name}</span><span class="tw-count">${total}</span><i data-lucide="chevron-down" class="tw-chev"></i>
          <button class="tree-dots" data-dot="qa-root" data-root-key="${root.key}" data-path="" data-name="${root.name}" title="更多操作"><i data-lucide="more-horizontal"></i></button>
        </div>
        <div class="tree-children${collapsed ? "" : " open"}">
          ${folders.map(f => qaFolderNodeHTML(f, "", root, setsByPath)).join("")}
          ${(setsByPath[""] || []).map(id => qaChildRowHTML(id, root, "")).join("")}
        </div>
      </div>`;
    });
    return html;
  }

  // 递归渲染用户文件夹节点（与输入库 treeNodeHTML 同构）
  function qaFolderNodeHTML(node, parentRel, root, setsByPath) {
    const rel = parentRel ? parentRel + "/" + node.name : node.name;
    const sets = setsByPath[rel] || [];
    // 计数：本目录 + 所有子目录下的问答对集数量
    const count = Object.keys(setsByPath)
      .filter(p => p === rel || p.startsWith(rel + "/"))
      .reduce((s, p) => s + setsByPath[p].length, 0);
    const collapsed = !!window.QA_COLLAPSED[`${root.key}:${rel}`];
    return `<div class="tree-node">
      <div class="tree-row${collapsed ? " collapsed" : ""}" data-qa-folder="1" data-root-key="${root.key}" data-path="${rel}" data-name="${node.name}">
        <i data-lucide="folder" class="tw-ic"></i><span class="tw-name">${node.name}</span><span class="tw-count">${count}</span><i data-lucide="chevron-down" class="tw-chev"></i>
        <button class="tree-dots" data-dot="qa-folder" data-root-key="${root.key}" data-path="${rel}" data-name="${node.name}" title="更多操作"><i data-lucide="more-horizontal"></i></button>
      </div>
      <div class="tree-children${collapsed ? "" : " open"}">
        ${(node.children || []).map(c => qaFolderNodeHTML(c, rel, root, setsByPath)).join("")}
        ${sets.map(id => qaChildRowHTML(id, root, rel)).join("")}
      </div>
    </div>`;
  }

  // 问答对集叶子节点
  function qaChildRowHTML(id, root, rel) {
    const doc = DOCS[id];
    const cnt = (doc.qa || []).filter(q => q.type === root.key).length;
    const active = state.sel.qa === id ? "active" : "";
    return `<div class="tree-row tree-child ${active}" data-dot="qa" data-id="${id}" data-type="${root.key}" data-root-key="${root.key}" data-path="${rel}" data-qa-id="${id}" data-qa-type="${root.key}" data-name="${doc.name}" draggable="true">
      <i data-lucide="file-text" class="tw-ic"></i><span class="tw-name">${doc.name}</span><span class="tw-count">${cnt} 条</span><span class="qa-badge ${root.key}">${root.name}</span><button class="tree-dots" data-dot="qa" data-id="${id}" data-type="${root.key}" data-root-key="${root.key}" data-path="${rel}" data-name="${doc.name}" title="更多操作"><i data-lucide="more-horizontal"></i></button>
    </div>`;
  }

  function bindQaTree(container) {
    syncTreeBody(container, qaTreeHTML());
    icons();
    // 文件夹行（系统根 + 用户文件夹）：折叠/展开（与输入库一致）+ 拖入接收
    container.querySelectorAll('.tree-row[data-qa-folder]').forEach(row => {
      row.addEventListener("click", (e) => {
        if (e.target.closest(".tree-dots")) return;
        const kids = row.closest(".tree-node").querySelector(".tree-children");
        if (kids) kids.classList.toggle("open");
        row.classList.toggle("collapsed");
        // 记住折叠态，重渲染后保持
        window.QA_COLLAPSED[`${row.dataset.rootKey}:${row.dataset.path || ""}`] = row.classList.contains("collapsed");
      });
      row.addEventListener("dragover", (e) => {
        e.preventDefault(); e.stopPropagation();
        const t = e.dataTransfer; const mType = t && t.getData("text/qa-type");
        if (mType && mType !== row.dataset.rootKey) { e.dataTransfer.dropEffect = "none"; return; }
        row.classList.add("drop-target");
      });
      row.addEventListener("dragleave", (e) => { if (!row.contains(e.relatedTarget)) row.classList.remove("drop-target"); });
      row.addEventListener("drop", async (e) => {
        e.preventDefault(); e.stopPropagation();
        row.classList.remove("drop-target");
        const mId = e.dataTransfer && e.dataTransfer.getData("text/qa-id");
        const mType = e.dataTransfer && e.dataTransfer.getData("text/qa-type");
        if (!mId) return;
        if (mType !== row.dataset.rootKey) { toast("仅可移动到相同目的（同为泛化或基础问题）的文件夹"); return; }
        await moveQaSetToFolder(mId, mType, row.dataset.path || "");
      });
    });
    // 问答对集节点：选中并展示 + 可拖拽到其他同目的文件夹
    container.querySelectorAll(".tree-child").forEach(row => {
      row.addEventListener("click", (e) => {
        if (e.target.closest(".tree-dots")) return;
        container.querySelectorAll(".tree-child.active").forEach(r => r.classList.remove("active"));
        row.classList.add("active");
        state.sel.qa = row.dataset.id;
        renderLibContent("qa", row.dataset.id);
      });
      row.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/qa-id", row.dataset.qaId);
        e.dataTransfer.setData("text/qa-type", row.dataset.qaType);
        e.dataTransfer.effectAllowed = "move";
      });
    });
    // 三点菜单：系统根 / 用户文件夹 / 问答对集（事件委托，避免图标替换导致 handler 丢失）
    container.addEventListener("click", (e) => {
      const btn = e.target.closest(".tree-dots");
      if (!btn) return;
      e.stopPropagation();
      const dot = btn.dataset.dot;
      if (dot === "qa-root") showQaRootContextMenu(e, btn);
      else if (dot === "qa-folder") showQaFolderContextMenu(e, btn);
      else showQaContextMenu(e, btn);
    });
  }

  // 将问答对集（= 某文档的全部同类问答对）移动到目标目录：调用后端逐条落库
  async function moveQaSetToFolder(docId, rootKey, targetRel) {
    const doc = DOCS[docId];
    if (!doc) return;
    const rows = (doc.qa || []).filter(q => q.type === rootKey);
    if (!rows.length) return;
    const cur = (rows.find(r => r.folderPath) || {}).folderPath || doc.qaFolderPath || "";
    if (cur === targetRel) { toast("已在目标目录"); return; }
    try {
      for (const r of rows) {
        if (!r.caseId) continue;
        const fd = new FormData();
        fd.append("folder_path", targetRel);
        const res = await fetch(API_BASE + `/api/cases/${r.caseId}/move`, { method: "POST", body: fd });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          toast(`移动失败：${err.detail || res.status}`, "warn");
          return;
        }
      }
    } catch (err) {
      toast("移动请求失败，请检查后端", "warn");
      return;
    }
    // 前端同步，避免整页重载
    rows.forEach(r => { r.folderPath = targetRel; });
    doc.qaFolderPath = targetRel;
    renderLib("qa");
    state.sel.qa = docId;
    renderLibContent("qa", docId);
    icons();
    toast(`已移动「${doc.name}」到「${targetRel || typeLabel(rootKey)}」`);
  }


  // 通用弹层构造：返回 pop 元素，调用方绑定 button.onclick
  function qaPopup(btn, html) {
    $$(".ctx-popup").forEach(p => p.remove());
    const pop = document.createElement("div");
    pop.className = "ctx-popup";
    pop.innerHTML = html;
    pop.style.visibility = "hidden";
    document.body.appendChild(pop);
    placePopup(pop, btn, 4, 8);
    bindPopupLifecycle(pop, btn, 4, 8);
    return pop;
  }

  // 问答对集三点菜单：导出 / 移动到 / 重命名 / 删除
  function showQaContextMenu(e, btn) {
    const id = btn.dataset.id;
    const rootKey = btn.dataset.rootKey || btn.dataset.type;
    const pop = qaPopup(btn, `<button data-act="qa-export">导出</button><button data-act="qa-move">移动到</button><button data-act="qa-rename">重命名</button><button data-act="qa-delete">删除</button>`);
    pop.querySelectorAll("button").forEach(b => {
      b.onclick = async () => {
        pop.remove();
        const act = b.dataset.act;
        if (act === "qa-export") exportQaSet(id);
        else if (act === "qa-move") showMoveQaModal(id, rootKey);
        else if (act === "qa-rename") renameQaSetInline(btn.closest(".tree-row"), id, rootKey);
        else if (act === "qa-delete") await deleteQaSet(id, rootKey);
      };
    });
  }

  // 系统根（泛化问题 / 基础问题）三点菜单：仅「新建文件夹」
  function showQaRootContextMenu(e, btn) {
    const rootKey = btn.dataset.rootKey;
    const pop = qaPopup(btn, `<button data-act="qa-newfolder">新建文件夹</button>`);
    pop.querySelectorAll("button").forEach(b => {
      b.onclick = async () => {
        pop.remove();
        if (b.dataset.act === "qa-newfolder") await createQaFolder("", rootKey);
      };
    });
  }

  // 用户文件夹三点菜单：导出 / 新建文件夹 / 重命名 / 删除
  function showQaFolderContextMenu(e, btn) {
    const rootKey = btn.dataset.rootKey;
    const rel = btn.dataset.path || "";
    const name = btn.dataset.name || "";
    const pop = qaPopup(btn, `<button data-act="qa-folder-export">导出</button><button data-act="qa-newfolder">新建文件夹</button><button data-act="qa-folder-rename">重命名</button><button data-act="qa-folder-delete">删除</button>`);
    pop.querySelectorAll("button").forEach(b => {
      b.onclick = async () => {
        pop.remove();
        const act = b.dataset.act;
        if (act === "qa-folder-export") exportQaFolder(rel, rootKey, name);
        else if (act === "qa-newfolder") await createQaFolder(rel, rootKey);
        else if (act === "qa-folder-rename") renameQaFolderInline(btn.closest(".tree-row"), rel, name);
        else if (act === "qa-folder-delete") await deleteQaFolder(rel, name);
      };
    });
  }

  // ---------------- 目录操作（复用 /api/folders，与输入库共享持久化目录） ----------------

  // 新建文件夹：parentRel 为空表示建在系统根下
  async function createQaFolder(parentRel, rootKey) {
    try {
      const fd = new FormData();
      fd.append("owner", CURRENT_USER);
      fd.append("name", "新建文件夹");
      if (parentRel) fd.append("parent_path", parentRel);
      const res = await fetch(API_BASE + "/api/folders", { method: "POST", body: fd });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast(`新建文件夹失败：${err.detail || res.status}`, "warn");
        return;
      }
      const created = await res.json();
      // 同步两棵树的数据源：QA_FOLDERS（问答对库）与 TREE（输入文档库共享同一份持久化目录）
      QA_FOLDERS.push({ folder_id: created.folder_id, name: created.name, parent_id: created.parent_id ?? null });
      const parentNode = parentRel ? (findOrCreateFolder(parentRel.split("/").pop()) || TREE) : TREE;
      if (parentNode && !(parentNode.children || []).some(c => c.name === created.name)) {
        (parentNode.children = parentNode.children || []).push({ name: created.name, children: [], folderId: created.folder_id });
      }
    } catch (err) {
      toast("新建文件夹请求失败，请检查后端", "warn");
      return;
    }
    // 展开父目录，便于看到新建项并直接进入重命名态
    window.QA_COLLAPSED[`${rootKey}:${parentRel}`] = false;
    renderLib("qa");
    const rel = parentRel ? parentRel + "/新建文件夹" : "新建文件夹";
    const row = $(`#qaTree .tree-row[data-qa-folder][data-root-key="${rootKey}"][data-path="${CSS.escape(rel)}"]`)
      || $$(`#qaTree .tree-row[data-qa-folder]`).find(r => r.dataset.path === rel && r.dataset.rootKey === rootKey);
    if (row) renameQaFolderInline(row, rel, "新建文件夹");
  }

  // 内联重命名文件夹：走 /api/folders/move（后端会一并重写文档与问答对的 folder_path）
  function renameQaFolderInline(row, rel, oldName) {
    if (!row) return;
    const nameSpan = row.querySelector(".tw-name");
    if (!nameSpan) return;
    const input = document.createElement("input");
    input.type = "text"; input.value = oldName; input.className = "tree-rename-input";
    input.style.cssText = "font-size:12.5px;padding:2px 6px;border:1px solid var(--brand);border-radius:6px;width:120px;outline:none;";
    nameSpan.replaceWith(input);
    input.focus(); input.select();
    let done = false;
    const commit = async () => {
      if (done) return; done = true;
      const v = input.value.trim();
      if (!v || v === oldName) { renderLib("qa"); return; }
      const parentRel = rel.split("/").slice(0, -1).join("/");
      const newRel = parentRel ? parentRel + "/" + v : v;
      try {
        const fd = new FormData();
        fd.append("owner", CURRENT_USER);
        fd.append("from_path", rel);
        fd.append("to_path", newRel);
        const res = await fetch(API_BASE + "/api/folders/move", { method: "PATCH", body: fd });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          toast(`重命名失败：${err.detail || res.status}`, "warn");
          renderLib("qa");
          return;
        }
      } catch (err) {
        toast("重命名请求失败，请检查后端", "warn");
        renderLib("qa");
        return;
      }
      // 目录改名会影响两个库的 folder_path，重新拉取后端数据保证一致
      await loadData();
      renderLib("qa");
      toast(`已重命名为「${v}」`);
    };
    input.addEventListener("keydown", e => { if (e.key === "Enter") commit(); if (e.key === "Escape") { done = true; renderLib("qa"); } });
    input.addEventListener("blur", commit);
  }

  // 删除文件夹：后端会把其下内容上移到父级
  // 统计某目录（含子孙）下归属的问答对条数
  function countQaUnder(rel) {
    let n = 0;
    for (const d of Object.values(DOCS)) {
      const fp = d.qaFolderPath || "";
      const under = rel ? (fp === rel || fp.startsWith(rel + "/")) : (fp === "" || fp === null);
      if (!under) continue;
      (d.qa || []).forEach(q => (q.children || []).forEach(c => { if (c.purpose) n++; }));
    }
    return n;
  }

  async function deleteQaFolder(rel, name) {
    const cnt = countQaUnder(rel);
    const tip = cnt > 0
      ? `该文件夹及其子目录下共有 <b>${cnt}</b> 条问答对，将<b>一并删除且不可恢复</b>。`
      : `该文件夹下没有问答对，仅删除空目录。`;
    const mask = document.createElement("div");
    mask.className = "up-modal-mask";
    mask.innerHTML = `
      <div class="up-modal" style="max-width:420px">
        <div class="up-modal-title">删除文件夹「${name}」</div>
        <div class="up-modal-body" style="line-height:1.7">
          ${tip}<br/>此操作不可恢复，确认继续？
        </div>
        <div class="up-modal-foot">
          <button class="up-btn" data-act="cancel">取消</button>
          <button class="up-btn primary" data-act="ok">确认删除</button>
        </div>
      </div>`;
    document.body.appendChild(mask);
    const close = () => mask.remove();
    mask.addEventListener("click", (e) => {
      if (e.target === mask || e.target.dataset.act === "cancel") return close();
      if (e.target.dataset.act === "ok") doDelete();
    });
    async function doDelete() {
      try {
        const res = await fetch(API_BASE + `/api/folders?path=${encodeURIComponent(rel)}&owner=${CURRENT_USER}`, { method: "DELETE" });
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          toast(`删除失败：${err.detail || res.status}`, "warn");
          return close();
        }
      } catch (err) {
        toast("删除请求失败，请检查后端", "warn");
        return close();
      }
      close();
      await loadData();
      renderLib("qa");
      toast(`已删除文件夹「${name}」${cnt > 0 ? `及 ${cnt} 条问答对` : ""}`);
    }
  }

  // 按目录导出（带目录结构）：直接下载后端生成的 JSON
  function exportQaFolder(rel, rootKey, name) {
    const purpose = rootKey === "gen" ? "gen" : "basic";
    const qs = new URLSearchParams({ recursive: "true", purpose });
    if (rel) qs.set("folder_path", rel);
    const url = API_BASE + `/api/cases/export-folder?` + qs.toString();
    const a = document.createElement("a");
    a.href = url; a.download = "";
    document.body.appendChild(a); a.click(); a.remove();
    toast(`正在导出「${name || typeLabel(rootKey)}」目录下的问答对（含目录结构）`);
  }

  // 重命名问答对集：改其下每条问答对的问题标题不合适，这里改「集名」= 源文档显示名
  function renameQaSetInline(row, docId, rootKey) {
    if (!row) return;
    const doc = DOCS[docId];
    if (!doc) return;
    const nameSpan = row.querySelector(".tw-name");
    if (!nameSpan) return;
    const oldName = doc.name;
    const input = document.createElement("input");
    input.type = "text"; input.value = oldName; input.className = "tree-rename-input";
    input.style.cssText = "font-size:12.5px;padding:2px 6px;border:1px solid var(--brand);border-radius:6px;width:140px;outline:none;";
    nameSpan.replaceWith(input);
    input.focus(); input.select();
    let done = false;
    const commit = () => {
      if (done) return; done = true;
      const v = input.value.trim();
      if (v && v !== oldName) {
        // 问答对集名即源文档显示名：仅前端展示层改名，不影响落盘文件与问答对内容
        doc.name = v;
        toast(`已重命名为「${v}」`);
      }
      renderLib("qa");
    };
    input.addEventListener("keydown", e => { if (e.key === "Enter") commit(); if (e.key === "Escape") { done = true; renderLib("qa"); } });
    input.addEventListener("blur", commit);
  }

  // 删除问答对集：删除该文档在此系统根下的全部问答对（逐条调后端）
  async function deleteQaSet(docId, rootKey) {
    const doc = DOCS[docId];
    if (!doc) return;
    const rows = (doc.qa || []).filter(q => q.type === rootKey);
    if (!rows.length) { toast("该问答对集为空"); return; }
    if (!confirm(`确认删除「${doc.name}」下的 ${rows.length} 条问答对？该操作不可撤销。`)) return;
    try {
      for (const r of rows) {
        if (!r.caseId) continue;
        const res = await fetch(API_BASE + `/api/cases/${r.caseId}`, { method: "DELETE" });
        if (!res.ok && res.status !== 404) {
          const err = await res.json().catch(() => ({}));
          toast(`删除失败：${err.detail || res.status}`, "warn");
          return;
        }
      }
    } catch (err) {
      toast("删除请求失败，请检查后端", "warn");
      return;
    }
    doc.qa = (doc.qa || []).filter(q => q.type !== rootKey);
    if (state.sel.qa === docId) state.sel.qa = null;
    renderLib("qa");
    toast(`已删除「${doc.name}」的 ${rows.length} 条问答对`);
  }

  // 「移动到」弹窗：列出可选目标目录（系统根 + 其下全部文件夹）
  function showMoveQaModal(docId, rootKey) {
    const doc = DOCS[docId];
    if (!doc) return;
    const root = QA_ROOTS.find(r => r.key === rootKey) || QA_ROOTS[1];
    // 扁平化全部目录路径
    const paths = [];
    (function walk(nodes, prefix) {
      nodes.forEach(n => {
        const rel = prefix ? prefix + "/" + n.name : n.name;
        paths.push(rel);
        if (n.children && n.children.length) walk(n.children, rel);
      });
    })(qaFolderTree(), "");
    const cur = (doc.qa.find(q => q.type === rootKey && q.folderPath) || {}).folderPath || doc.qaFolderPath || "";
    const opts = [{ rel: "", label: root.name }].concat(paths.map(p => ({ rel: p, label: root.name + "/" + p })));
    const mask = document.createElement("div");
    mask.className = "up-modal-mask";
    mask.innerHTML = `<div class="up-modal">` +
      `<div class="up-modal-head"><span>移动「${doc.name}」到目标目录</span><button class="up-close" title="关闭">×</button></div>` +
      `<div class="up-modal-body"><div class="up-tree">` +
      opts.map(o => `<label class="up-node mv-opt" style="display:flex;align-items:center;gap:8px;cursor:pointer">
          <input type="radio" name="mvQa" value="${o.rel}"${o.rel === cur ? " checked" : ""}>
          <i data-lucide="folder"></i><span>${o.label}</span>${o.rel === cur ? '<span class="muted">（当前）</span>' : ""}
        </label>`).join("") +
      `</div></div>` +
      `<div class="up-modal-foot"><button class="up-confirm">移动到此处</button></div>` +
      `<div class="up-hint">问答对集将移动到所选目录，目录归属会持久化到后端；拖拽问答对集到左侧目录树同样可以移动。</div>` +
      `</div>`;
    document.body.appendChild(mask);
    icons();
    const close = () => mask.remove();
    mask.querySelector(".up-close").onclick = close;
    mask.addEventListener("click", (e) => { if (e.target === mask) close(); });
    mask.querySelector(".up-confirm").onclick = async () => {
      const picked = mask.querySelector('input[name="mvQa"]:checked');
      const target = picked ? picked.value : "";
      close();
      await moveQaSetToFolder(docId, rootKey, target);
    };
  }
  function reviewBadge(r) {
    const map = { "已通过": "ok", "已驳回": "bad", "待审核": "warn" };
    return `<span class="review-badge ${map[r.review] || "warn"}">${r.review}</span>`;
  }
  // 审核比例统计：通过 / 驳回 / 待审核
  function reviewRatio(rows) {
    const r = { total: rows.length, pass: 0, reject: 0, pending: 0 };
    rows.forEach(x => {
      if (x.review === "已通过") r.pass++;
      else if (x.review === "已驳回") r.reject++;
      else r.pending++;
    });
    return r;
  }
  function qaRowHTML(q) {
    // 仿 Excel：问题/答案分列，证据为原文语句，来源文档用 / 分级显示，类型标识 基础问题 / 泛化问题
    return `<div class="qa-row" data-id="${q.id}">
      <div class=" qa-cell qa-q-cell" data-c="q"><span title="${escapeHTML(q.q)}">${escapeHTML(q.q)}</span></div>
      <div class="qa-cell qa-a-cell" data-c="a"><span title="${escapeHTML(q.a)}">${escapeHTML(q.a)}</span></div>
      <div class="qa-cell qa-diff-cell" data-c="diff"><span>${escapeHTML(q.diff)}</span></div>
      <div class="qa-cell qa-review-cell" data-c="review">${reviewBadge(q)}</div>
      <div class="qa-cell qa-ev-cell" data-c="evidence"><span title="${escapeHTML(q.evidence || "（无）")}">${escapeHTML(q.evidence || "（无）")}</span></div>
      <div class="qa-cell qa-src-cell" data-c="src"><span title="${escapeHTML(q.src || "（无）")}">${escapeHTML(q.src || "（无）")}</span></div>
      <div class="qa-cell qa-type-cell"><span class="qa-badge ${q.type}">${typeLabel(q.type)}</span></div>
      <span class="ds-actions">
        <button class="btn ghost sm" data-act="qa-del" title="删除"><i data-lucide="trash-2"></i></button>
      </span>
    </div>`;
  }
  function qaBlockHTML(rows, chartId, addDocId) {
    // 难度分布：简单 / 中等 / 难
    const c = { "简单": 0, "中等": 0, "难": 0 };
    rows.forEach(r => { c[r.diff] = (c[r.diff] || 0) + 1; });
    // 质量与人工审核：显示完整问答对 + 通过/驳回比例（去掉质量均分）
    const rr = reviewRatio(rows);
    const review = rows.filter(r => r.review === "待审核");
    return `
      <div class="sec-toggle qa-review-toggle" id="qaReviewToggle"><span class="t-arr">▸</span>质量与人工审核（通过 / 驳回比例）</div>
      <div class="ds-grid">
        <div class="ds-block"><div class="ds-title">难度分布（简单 / 中等 / 难）</div><div class="chart-box"><canvas id="${chartId}"></canvas></div></div>
        <div class="ds-block qa-review-block collapsed" id="qaReviewBlock"><div class="ds-title">质量与人工审核（通过 / 驳回比例）</div>
          <div class="stat-row"><span>通过比例</span><b>${rr.total ? Math.round(rr.pass / rr.total * 100) : 0}%</b></div>
          <div class="stat-row"><span>驳回比例</span><b>${rr.total ? Math.round(rr.reject / rr.total * 100) : 0}%</b></div>
          <div class="stat-row"><span>待审核</span><b>${rr.pending}</b></div>
          <div class="review-list mt"><div class="review-tip">待审核问答对（需人工查看完整内容）</div>${review.length ? review.map(r => `<div class="review-item"><div class="ri-q">${r.q}</div><div class="ri-a">${r.a}</div><div class="ri-actions"><button class="btn ghost sm" data-rv="pass" data-id="${r.id}"><i data-lucide="check"></i>通过</button><button class="btn ghost sm" data-rv="rej" data-id="${r.id}"><i data-lucide="x"></i>驳回</button></div></div>`).join("") : '<div class="muted">无待审核项</div>'}</div>
        </div>
      </div>
      <div class="sec-h mt">问答对</div>
      <div class="qa-toolbar">
        <div class="qa-add-wrap">
          <button class="btn primary sm" data-act="qa-add"><i data-lucide="plus"></i>新增问答对</button>
          <div class="qa-add-menu" id="qaAddMenu">
            <button data-add="single">新增单个问答对</button>
            <button data-add="file">从文件导入（含质量门禁审核）</button>
            <button data-add="tmpl">下载新增模板</button>
          </div>
        </div>
        <button class="btn ghost sm" id="qaExportBtn"><i data-lucide="download"></i>导出问答对</button>
        <div class="qa-toolbar-right">
          <div class="qa-search"><i data-lucide="search"></i><input id="qaSearch" type="text" placeholder="搜索问题/答案/证据/来源…" /></div>
          <button class="btn ghost icon-only sm" id="qaFullscreenBtn" title="全屏查看"><i data-lucide="maximize"></i></button>
        </div>
      </div>
      <div class="card card-pad">
        <div class="qa-table" id="qaTable">
          <div class="qa-col-head">
            <div class="qa-cell qa-q-cell">问题<span class="col-filter" data-filter="q"><i data-lucide="filter"></i></span><span class="qa-resize" data-resize="0"></span></div>
            <div class="qa-cell qa-a-cell">答案<span class="col-filter" data-filter="a"><i data-lucide="filter"></i></span><span class="qa-resize" data-resize="1"></span></div>
            <div class="qa-cell qa-diff-cell">难度<span class="col-filter" data-filter="diff"><i data-lucide="filter"></i></span><span class="qa-resize" data-resize="2"></span></div>
            <div class="qa-cell qa-review-cell">审核<span class="col-filter" data-filter="review"><i data-lucide="filter"></i></span><span class="qa-resize" data-resize="3"></span></div>
            <div class="qa-cell qa-ev-cell">证据<span class="col-filter" data-filter="evidence"><i data-lucide="filter"></i></span><span class="qa-resize" data-resize="4"></span></div>
            <div class="qa-cell qa-src-cell">来源文档<span class="col-filter" data-filter="src"><i data-lucide="filter"></i></span><span class="qa-resize" data-resize="5"></span></div>
            <div class="qa-cell qa-type-cell">类型<span class="col-filter" data-filter="type"><i data-lucide="filter"></i></span><span class="qa-resize" data-resize="6"></span></div>
            <div class="qa-cell qa-act-cell">操作</div>
          </div>
          <div id="qaRows">${rows.map(qaRowHTML).join("")}</div>
        </div>
      </div>`;
  }
  function findDocOfQa(qid) { for (const id in DOCS) if (DOCS[id].qa.some(q => q.id === qid)) return id; return null; }
  function currentQaDoc() {
    if (state.folderSel.qa) { const ids = descendantDocs(findNode(state.folderSel.qa)); return ids[0]; }
    return state.sel.qa;
  }
  // 当前 qalib 选中范围内的全部问答对（文档详情或目录聚合）
  function currentQaRows() {
    if (state.folderSel.qa) {
      const ids = descendantDocs(findNode(state.folderSel.qa));
      return ids.flatMap(i => DOCS[i] ? DOCS[i].qa : []);
    }
    const id = state.sel.qa;
    return id && DOCS[id] ? DOCS[id].qa : [];
  }
  function addQa(docId, preset) {
    const base = { id: "Q-" + (Date.now() % 100000), q: "新问题（点击单元格编辑）", a: "待补充答案", diff: "简单", review: "待审核", evidence: "（无）", src: "（无）" };
    DOCS[docId].qa.push(Object.assign(base, preset || {}));
    state.folderSel.qa = null; state.sel.qa = docId; showLib("qa");
  }
  function qaBind(chartId) {
    const cv = document.getElementById(chartId);
    if (cv) {
      const rows = $$("#qaRows .qa-row");
      const c = { "简单": 0, "中等": 0, "难": 0 };
      rows.forEach(r => { const t = r.querySelector(".qa-diff-cell span").textContent.trim(); c[t] = (c[t] || 0) + 1; });
      if (charts[chartId]) charts[chartId].destroy();
      if (window.Chart) charts[chartId] = new Chart(cv, {
        type: "doughnut",
        data: { labels: ["简单", "中等", "难"], datasets: [{ data: [c["简单"], c["中等"], c["难"]], backgroundColor: ["#5FBF97", "#E0A85E", "#E08AA0"], borderWidth: 0 }] },
        options: { maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { font: { size: 11 } } } } }
      });
    }
    const addBtn = $("#qaContent [data-act='qa-add']");
    if (addBtn) addBtn.onclick = (e) => { e.stopPropagation(); const m = $("#qaAddMenu"); if (m) m.classList.toggle("open"); };
    const addMenu = $("#qaAddMenu");
    if (addMenu) addMenu.querySelectorAll("button").forEach(b => {
      b.onclick = () => {
        addMenu.classList.remove("open");
        if (b.dataset.add === "single") addQa(currentQaDoc());
        else if (b.dataset.add === "file") openQaFileImport();
        else if (b.dataset.add === "tmpl") downloadQaTemplate();
      };
    });
    // 每列筛选
    $$("#qaContent .col-filter").forEach(f => {
      f.onclick = (e) => { e.stopPropagation(); openColFilter(f.dataset.filter, f); };
    });
    // 单击显示单元格全文
    $$("#qaContent .qa-row .qa-cell[data-c]").forEach(cell => {
      cell.addEventListener("click", () => {
        if (cell.dataset._editing) return;
        const t = setTimeout(() => showCellFull(cell), 220);
        cell.addEventListener("click", () => clearTimeout(t), { once: true });
      });
    });
    // 列宽拖拽调整
    bindQaColResize();
    $$("#qaContent .qa-row").forEach(row => {
      const id = row.dataset.id;
      const del = row.querySelector("[data-act='qa-del']");
      if (del) del.onclick = () => {
        const d = DOCS[findDocOfQa(id)];
        if (!confirm("删除该问答对？")) return;
        d.qa = d.qa.filter(x => x.id !== id); showLib("qa");
      };
    });
    const exp = $("#qaExportBtn");
    if (exp) exp.onclick = () => {
      const rows = currentQaRows();
      const name = state.folderSel.qa ? state.folderSel.qa : (state.sel.qa && DOCS[state.sel.qa] ? DOCS[state.sel.qa].name : "问答对集");
      exportQaRows(rows, name);
    };
    // 文本搜索过滤（跨 问题/答案/证据/来源文档）
    const search = $("#qaSearch");
    if (search) search.oninput = () => {
      const kw = search.value.trim().toLowerCase();
      $$("#qaRows .qa-row").forEach(row => {
        if (!kw) { row.style.display = ""; delete row.dataset.filtered; return; }
        const txt = row.textContent.toLowerCase();
        if (txt.includes(kw)) { row.style.display = ""; delete row.dataset.filtered; }
        else { row.style.display = "none"; row.dataset.filtered = "1"; }
      });
      state.qaPage = 1; setupPager($("#qaContent"), "#qaRows .qa-row", 15, "qaPager", "qaPage");
    };
    // 全屏放大查看
    const fsBtn = $("#qaFullscreenBtn");
    if (fsBtn) fsBtn.onclick = () => openQaFullscreen(currentQaRows(), state.sel.qa && DOCS[state.sel.qa] ? DOCS[state.sel.qa].name : (state.folderSel.qa || "问答对集"));
    $$("#qaContent [data-rv]").forEach(b => {
      b.onclick = () => {
        const d = DOCS[findDocOfQa(b.dataset.id)]; const q = d.qa.find(x => x.id === b.dataset.id);
        if (!q) return; q.review = b.dataset.rv === "pass" ? "已通过" : "已驳回"; showLib("qa");
      };
    });
    bindQaReviewToggle($("#qaContent"));
    // 分页（每页 15）+ 横向拖动/滚轮查看全局
    setupPager($("#qaContent"), "#qaRows .qa-row", 15, "qaPager", "qaPage");
    enableHScrollDrag($("#qaContent .qa-table"));
  }

  // 全屏放大查看问答对（独立浮层，内容占满浏览器）
  function openQaFullscreen(rows, name) {
    if (!rows.length) { toast("当前没有可查看的问答对"); return; }
    $$(".qa-fullscreen").forEach(e => e.remove());
    const overlay = document.createElement("div");
    overlay.className = "qa-fullscreen";
    overlay.innerHTML = `
      <div class="qaf-bar">
        <div class="qaf-title">问答对查看 · ${escapeHTML(name)}</div>
        <div class="qaf-actions">
          <div class="qa-search"><i data-lucide="search"></i><input id="qafSearch" type="text" placeholder="搜索问题/答案/证据/来源…" /></div>
          <button class="btn ghost icon-only sm" id="qafClose" title="退出全屏"><i data-lucide="minimize"></i></button>
        </div>
      </div>
      <div class="qaf-body"><div class="lib-head"><div class="lh-ic"><i data-lucide="message-square-text"></i></div><div><div class="lh-title">${escapeHTML(name)}</div><div class="lh-sub">问答对 · ${rows.length} 条</div></div></div>${qaBlockHTML(rows, "qaFsChart")}</div>`;
    document.body.appendChild(overlay);
    document.body.style.overflow = "hidden";
    const cId = "qaFsChart";
    setTimeout(() => {
      // 图表
      const cv = document.getElementById(cId);
      if (cv && window.Chart) {
        const c = { "简单": 0, "中等": 0, "难": 0 };
        rows.forEach(r => { c[r.diff] = (c[r.diff] || 0) + 1; });
        new Chart(cv, { type: "doughnut", data: { labels: ["简单", "中等", "难"], datasets: [{ data: [c["简单"], c["中等"], c["难"]], backgroundColor: ["#5FBF97", "#E0A85E", "#E08AA0"], borderWidth: 0 }] }, options: { maintainAspectRatio: false, cutout: "62%", plugins: { legend: { position: "bottom", labels: { font: { size: 11 } } } } } });
      }
      // 单元格：点击显示全文 + 编辑
      bindQaCellInteractions(overlay);
      bindQaReviewToggle(overlay);
      // 列筛选
      overlay.querySelectorAll(".col-filter").forEach(f => { f.onclick = (e) => { e.stopPropagation(); openColFilter(f.dataset.filter, f); }; });
      bindQaColResizeIn(overlay.querySelector("#qaTable"));
      // 搜索
      const s = overlay.querySelector("#qafSearch");
      if (s) s.oninput = () => {
        const kw = s.value.trim().toLowerCase();
        overlay.querySelectorAll("#qaRows .qa-row").forEach(row => {
          if (!kw) { row.style.display = ""; delete row.dataset.filtered; return; }
          if (row.textContent.toLowerCase().includes(kw)) { row.style.display = ""; delete row.dataset.filtered; }
          else { row.style.display = "none"; row.dataset.filtered = "1"; }
        });
        setupPager(overlay, "#qaRows .qa-row", 15, "qaFsPager", "qaPage");
      };
      icons();
      setupPager(overlay, "#qaRows .qa-row", 15, "qaFsPager", "qaPage");
      enableHScrollDrag(overlay.querySelector(".qa-table"));
    }, 0);
    overlay.querySelector("#qafClose").onclick = () => { overlay.remove(); document.body.style.overflow = ""; };
    overlay.addEventListener("click", (e) => { if (e.target === overlay) { overlay.remove(); document.body.style.overflow = ""; } });
  }
  // 放大查看知识点（全浏览器），可再点「缩小」退出
  function openKpFullscreen(all, name) {
    if (!all || !all.length) { toast("当前文档没有知识点"); return; }
    $$(".kp-fullscreen").forEach(e => e.remove());
    const overlay = document.createElement("div");
    overlay.className = "kp-fullscreen";
    overlay.innerHTML = `
      <div class="qaf-bar">
        <div class="qaf-title">知识点查看 · ${escapeHTML(name)}</div>
        <div class="qaf-actions">
          <div class="qa-search"><i data-lucide="search"></i><input id="kpfSearch" type="text" placeholder="搜索知识点/证据/来源…" /></div>
          <button class="btn ghost icon-only sm" id="kpfClose" title="缩小"><i data-lucide="minimize"></i></button>
        </div>
      </div>
      <div class="qaf-body"><div class="lib-head"><div class="lh-ic"><i data-lucide="list-checks"></i></div><div><div class="lh-title">${escapeHTML(name)}</div><div class="lh-sub">知识点 · ${all.length} 条</div></div></div>${kpTableHTML(all)}</div>`;
    document.body.appendChild(overlay);
    document.body.style.overflow = "hidden";
    setTimeout(() => {
      const s = overlay.querySelector("#kpfSearch");
      if (s) s.oninput = () => {
        const kw = s.value.trim().toLowerCase();
        overlay.querySelectorAll(".kp-tr").forEach(row => {
          if (!kw) { row.style.display = ""; delete row.dataset.filtered; return; }
          if (row.textContent.toLowerCase().includes(kw)) { row.style.display = ""; delete row.dataset.filtered; }
          else { row.style.display = "none"; row.dataset.filtered = "1"; }
        });
        setupPager(overlay, ".kp-tr", 15, "kpFsPager", "kpPage");
      };
      icons();
      bindKpColFilters(overlay);
      bindKpColResize(overlay.querySelector(".kp-table"));
      setupPager(overlay, ".kp-tr", 15, "kpFsPager", "kpPage");
      enableHScrollDrag(overlay.querySelector(".kp-table"));
    }, 0);
    overlay.querySelector("#kpfClose").onclick = () => { overlay.remove(); document.body.style.overflow = ""; };
    overlay.addEventListener("click", (e) => { if (e.target === overlay) { overlay.remove(); document.body.style.overflow = ""; } });
  }
  // 在指定容器内绑定「质量与人工审核」展开/收回（箭头向下展开、向上收回）
  function bindQaReviewToggle(scope) {
    const tg = scope.querySelector("#qaReviewToggle");
    const blk = scope.querySelector("#qaReviewBlock");
    if (!tg || !blk) return;
    tg.onclick = () => {
      const collapsed = blk.classList.toggle("collapsed");
      const arr = tg.querySelector(".t-arr");
      if (arr) arr.textContent = collapsed ? "▸" : "▾";
    };
  }
  // 在指定容器内绑定问答对单元格交互（点击显示全文 + 双击编辑），供主视图与全屏共用
  function bindQaCellInteractions(scope) {
    scope.querySelectorAll(".qa-row .qa-cell[data-c]").forEach(cell => {
      cell.addEventListener("click", () => {
        if (cell.dataset._editing) return;
        const t = setTimeout(() => showCellFull(cell), 220);
        cell.addEventListener("click", () => clearTimeout(t), { once: true });
      });
    });
  }
  // 在指定表格内绑定列宽拖拽
  function bindQaColResizeIn(table) {
    if (!table) return;
    const defCols = [220, 300, 72, 92, 300, 200, 110, 76];
    const cur = () => {
      const v = getComputedStyle(table).getPropertyValue("--qa-cols");
      if (v && v.trim()) return v.trim().split(/\s+/).map(s => parseFloat(s));
      return defCols.slice();
    };
    const apply = (cols) => { table.style.setProperty("--qa-cols", cols.map(c => Math.max(56, c) + "px").join(" ")); table.dispatchEvent(new Event("scroll")); };
    apply(cur());
    table.querySelectorAll(".qa-resize").forEach(handle => {
      handle.onmousedown = (e) => {
        e.preventDefault(); e.stopPropagation();
        const idx = parseInt(handle.dataset.resize, 10);
        const startX = e.clientX; const startW = cur()[idx]; handle.classList.add("active");
        const move = (ev) => { const cols = cur(); cols[idx] = Math.max(56, startW + (ev.clientX - startX)); apply(cols); };
        const up = () => { handle.classList.remove("active"); document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
        document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
      };
    });
  }
  // 点击单元格：弹出浮层显示该单元格全部文字
  const QA_COL_NAMES = { q: "问题", a: "答案", diff: "难度", evidence: "证据", src: "来源文档" };
  function showCellFull(cell) {
    const c = cell.dataset.c;
    const span = cell.querySelector("span");
    const txt = (span ? span.textContent : cell.textContent).trim();
    if (!txt || txt === "—") return;
    $$(".cell-popover").forEach(p => p.remove());
    const pop = document.createElement("div");
    pop.className = "cell-popover wide";
    let editor = "";
    // 可编辑字段：问题/答案/证据/来源用多行文本；难度/审核用下拉
    if (["q", "a", "evidence", "src"].includes(c)) {
      editor = `<textarea class="cell-edit-area" data-edit="${c}">${escapeHTML(txt)}</textarea><div class="cell-pop-actions"><button class="btn primary sm" data-save>保存</button><button class="btn ghost sm" data-cancel>取消</button></div>`;
    } else if (c === "diff") {
      editor = `<select class="cell-edit-area" data-edit="diff">${["简单", "中等", "难"].map(v => `<option ${v === txt ? "selected" : ""}>${v}</option>`).join("")}</select><div class="cell-pop-actions"><button class="btn primary sm" data-save>保存</button><button class="btn ghost sm" data-cancel>取消</button></div>`;
    } else if (c === "review") {
      editor = `<select class="cell-edit-area" data-edit="review">${["已通过", "已驳回", "待审核"].map(v => `<option ${v === txt ? "selected" : ""}>${v}</option>`).join("")}</select><div class="cell-pop-actions"><button class="btn primary sm" data-save>保存</button><button class="btn ghost sm" data-cancel>取消</button></div>`;
    }
    pop.innerHTML = `<div class="cell-pop-title">${QA_COL_NAMES[c] || "内容"}</div><div class="cell-pop-body">${escapeHTML(txt)}</div>${editor}`;
    document.body.appendChild(pop);
    const r = cell.getBoundingClientRect();
    let top = window.scrollY + r.bottom + 6;
    let left = window.scrollX + r.left;
    const maxW = Math.min(560, window.innerWidth - 20);
    pop.style.maxWidth = maxW + "px";
    if (left + 560 > window.scrollX + window.innerWidth - 10) left = window.scrollX + window.innerWidth - 560 - 10;
    pop.style.top = top + "px";
    pop.style.left = Math.max(10, left) + "px";
    // 编辑保存：直接写回数据并刷新视图
    const saveBtn = pop.querySelector("[data-save]");
    if (saveBtn) saveBtn.onclick = () => {
      const row = cell.closest(".qa-row"); const id = row ? row.dataset.id : null;
      const d = id ? DOCS[findDocOfQa(id)] : null; const q = d ? d.qa.find(x => x.id === id) : null;
      if (q) { const f = pop.querySelector("[data-edit]").value.trim(); q[c] = f; showLib("qa"); }
      pop.remove();
    };
    const cancelBtn = pop.querySelector("[data-cancel]");
    if (cancelBtn) cancelBtn.onclick = () => pop.remove();
    const close = (ev) => {
      if (!pop.contains(ev.target) && !cell.contains(ev.target)) { pop.remove(); document.removeEventListener("click", close); }
    };
    setTimeout(() => document.addEventListener("click", close), 0);
  }
  // 列宽拖拽调整
  function bindQaColResize() {
    const table = $("#qaTable"); if (!table) return;
    const colCount = 8;
    const defCols = [220, 300, 72, 92, 300, 200, 110, 76];
    const cur = () => {
      const v = getComputedStyle(table).getPropertyValue("--qa-cols");
      if (v && v.trim()) return v.trim().split(/\s+/).map(s => parseFloat(s));
      return defCols.slice();
    };
    const apply = (cols) => { table.style.setProperty("--qa-cols", cols.map(c => Math.max(56, c) + "px").join(" ")); table.dispatchEvent(new Event("scroll")); };
    apply(cur());
    $$("#qaContent .qa-resize").forEach(handle => {
      handle.onmousedown = (e) => {
        e.preventDefault(); e.stopPropagation();
        const idx = parseInt(handle.dataset.resize, 10);
        const startX = e.clientX;
        const startW = cur()[idx];
        handle.classList.add("active");
        const move = (ev) => {
          const cols = cur();
          cols[idx] = Math.max(56, startW + (ev.clientX - startX));
          apply(cols);
        };
        const up = () => {
          handle.classList.remove("active");
          document.removeEventListener("mousemove", move);
          document.removeEventListener("mouseup", up);
        };
        document.addEventListener("mousemove", move);
        document.addEventListener("mouseup", up);
      };
    });
  }

  // 列筛选弹层
  const colFilterLabel = { q: "问题", a: "答案", diff: "难度", review: "审核", evidence: "证据", src: "来源文档", type: "类型" };
  function openColFilter(field, anchor) {
    $$(".ctx-popup").forEach(p => p.remove());
    const docId = currentQaDoc(); const d = DOCS[docId]; if (!d) return;
    const vals = [...new Set(d.qa.map(q => field === "review" ? q.review : (q[field] || "—")))].filter(Boolean);
    const pop = document.createElement("div"); pop.className = "ctx-popup col-filter-pop";
    pop.innerHTML = `<div class="up-title">筛选：${colFilterLabel[field] || field}</div>` + vals.map(v => `<label class="cf-item"><input type="checkbox" checked data-v="${v}"/> ${v}</label>`).join("") + `<button class="cf-apply">应用</button>`;
    pop.style.visibility = "hidden";
    document.body.appendChild(pop);
    placePopup(pop, anchor || { getBoundingClientRect: () => ({ bottom: 200, left: 200, right: 200, top: 200, width: 0, height: 0 }) }, 6, 8);
    bindPopupLifecycle(pop, anchor, 6, 8);
    const cellClass = { q: "qa-q-cell", a: "qa-a-cell", diff: "qa-diff-cell", review: "qa-review-cell", evidence: "qa-ev-cell", src: "qa-src-cell", type: "qa-type-cell" };
    pop.querySelector(".cf-apply").onclick = () => {
      const keep = new Set([...pop.querySelectorAll("input[data-v]:checked")].map(x => x.dataset.v));
      const cls = cellClass[field] || `qa-${field}-cell`;
      $$("#qaRows .qa-row").forEach(row => {
        const cell = row.querySelector("." + cls);
        const f = field === "review" ? (cell ? cell.textContent.trim() : "—") : ((cell && cell.querySelector("span")) ? cell.querySelector("span").textContent.trim() : "—");
        if (keep.has(f)) { row.style.display = ""; delete row.dataset.filtered; }
        else { row.style.display = "none"; row.dataset.filtered = "1"; }
      });
      state.qaPage = 1; refreshPagers(); pop.remove();
    };
  }

  // 知识点表格列筛选（与问答对列筛选机制一致）
  const kpColFilterLabel = { stmt: "知识点", prio: "推荐", type: "类型", ev: "证据", src: "来源文档" };
  function openKpColFilter(field, anchor) {
    $$(".ctx-popup").forEach(p => p.remove());
    const pop = document.createElement("div"); pop.className = "ctx-popup col-filter-pop";
    const cells = $$(`.kp-c-${field}`);
    const vals = [...new Set(cells.map(c => c.textContent.replace(/^#\d+\s*/, "").trim()).filter(Boolean))];
    pop.innerHTML = `<div class="up-title">筛选：${kpColFilterLabel[field] || field}</div>` + vals.map(v => `<label class="cf-item"><input type="checkbox" checked data-v="${escapeHTML(v)}"/> ${escapeHTML(v)}</label>`).join("") + `<button class="cf-apply">应用</button>`;
    pop.style.visibility = "hidden";
    document.body.appendChild(pop);
    placePopup(pop, anchor || { getBoundingClientRect: () => ({ bottom: 200, left: 200, right: 200, top: 200, width: 0, height: 0 }) }, 6, 8);
    bindPopupLifecycle(pop, anchor, 6, 8);
    pop.querySelector(".cf-apply").onclick = () => {
      const keep = new Set([...pop.querySelectorAll("input[data-v]:checked")].map(x => x.dataset.v));
      $$(`.kp-table .kp-tr`).forEach(row => {
        const cell = row.querySelector(`.kp-c-${field}`);
        const f = cell ? cell.textContent.replace(/^#\d+\s*/, "").trim() : "—";
        if (keep.has(f)) { row.style.display = ""; delete row.dataset.filtered; }
        else { row.style.display = "none"; row.dataset.filtered = "1"; }
      });
      state.kpPage = 1; refreshPagers(); pop.remove();
    };
  }
  function bindKpColFilters(scope) {
    (scope || document).querySelectorAll(".kp-table .col-filter").forEach(icon => {
      icon.onclick = (e) => { e.stopPropagation(); openKpColFilter(icon.dataset.filter, icon); };
    });
  }
  // 知识点表格列宽拖拽调整（与主问答对表一致）
  function bindKpColResize(table) {
    if (!table) return;
    const defCols = [320, 96, 110, 220, 220];
    const cur = () => {
      const v = getComputedStyle(table).getPropertyValue("--kp-cols");
      if (v && v.trim()) return v.trim().split(/\s+/).map(s => parseFloat(s));
      return defCols.slice();
    };
    const apply = (cols) => { table.style.setProperty("--kp-cols", cols.map(c => Math.max(56, c) + "px").join(" ")); table.dispatchEvent(new Event("scroll")); };
    apply(cur());
    table.querySelectorAll(".kp-resize").forEach(handle => {
      handle.onmousedown = (e) => {
        e.preventDefault(); e.stopPropagation();
        const idx = parseInt(handle.dataset.resize, 10);
        const startX = e.clientX; const startW = cur()[idx]; handle.classList.add("active");
        // 阻止拖拽时触发单元格点击/筛选
        const move = (ev) => { const cols = cur(); cols[idx] = Math.max(56, startW + (ev.clientX - startX)); apply(cols); };
        const up = () => { handle.classList.remove("active"); document.removeEventListener("mousemove", move); document.removeEventListener("mouseup", up); };
        document.addEventListener("mousemove", move); document.addEventListener("mouseup", up);
      };
    });
  }

  // 滚动容器增强：鼠标滚轮可竖向查看内容；Shift+滚轮（或触摸板纯横向）可横向查看；
  // 按住空白处可左右拖动看全局。注意：竖向滚轮不拦截，交给原生滚动，避免表格卡死看不见上下内容。
  function enableHScrollDrag(el) {
    if (!el || el._hDragBound) return; el._hDragBound = true;
    el.classList.add("scroll-drag");
    let down = false, startX = 0, startLeft = 0, moved = false;
    el.addEventListener("mousedown", (e) => {
      if (e.target.closest("button, input, .col-filter, a, .qa-resize, .kp-resize, .qa-cell-editable")) return;
      down = true; moved = false; startX = e.pageX; startLeft = el.scrollLeft; el.classList.add("dragging");
    });
    window.addEventListener("mouseup", () => { down = false; el.classList.remove("dragging"); });
    window.addEventListener("mousemove", (e) => {
      if (!down) return;
      const dx = e.pageX - startX;
      if (Math.abs(dx) > 3) moved = true;
      el.scrollLeft = startLeft - dx;
    });
    // 阻止拖动误触发单元格点击
    el.addEventListener("click", (e) => { if (moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
    // 横向滚动：Shift+滚轮 / 纯横向(deltaX) 直接横向；普通竖向滚轮滚到顶或底边界时自动转为横向（普通鼠标也能看右侧列）
    el.addEventListener("wheel", (e) => {
      const horiz = e.shiftKey || (Math.abs(e.deltaX) > Math.abs(e.deltaY));
      if (horiz) {
        el.scrollLeft += (e.deltaX !== 0 ? e.deltaX : e.deltaY);
        e.preventDefault();
        return;
      }
      if (el.scrollWidth > el.clientWidth + 1) {
        const atTop = el.scrollTop <= 0;
        const atBottom = el.scrollTop + el.clientHeight >= el.scrollHeight - 1;
        if ((atTop && e.deltaY < 0) || (atBottom && e.deltaY > 0)) {
          el.scrollLeft += e.deltaY;
          e.preventDefault();
        }
      }
    }, { passive: false });
  }

  // 分页：每页 perPage 条，可翻页 + 输入页码跳转；与列筛选/搜索叠加（仅对当前可见行分页）
  function setupPager(scope, rowSel, perPage, pagerId, pageKey) {
    const sc = scope || document;
    const all = [...sc.querySelectorAll(rowSel)];
    if (!all.length) return;
    // 仅对「未被列筛选/搜索隐藏」的行分页（用 dataset.filtered 标记，避免分页自身隐藏状态干扰）
    const vis = all.filter(r => r.dataset.filtered !== "1");
    state[pageKey] = state[pageKey] || 1;
    const total = vis.length;
    const pages = Math.max(1, Math.ceil(total / perPage));
    if (state[pageKey] > pages) state[pageKey] = pages;
    const cur = state[pageKey];
    all.forEach(r => { if (r.style.display !== "none") r.style.display = "none"; });
    vis.forEach((r, i) => {
      r.style.display = (i >= (cur - 1) * perPage && i < cur * perPage) ? "" : "none";
    });
    // 分页条挂载到表格容器同级（在表格后面）
    let holder = sc.querySelector("#" + pagerId);
    if (!holder) {
      holder = document.createElement("div"); holder.id = pagerId; holder.className = "pager";
      const table = sc.querySelector(".qa-table, .kp-table");
      if (table && table.parentNode) table.parentNode.insertBefore(holder, table.nextSibling);
    }
    holder.innerHTML = `
      <button data-pg="prev" ${cur <= 1 ? "disabled" : ""}>‹ 上一页</button>
      <span class="pg-info">第</span><input type="number" min="1" max="${pages}" value="${cur}" data-pg-input />
      <span class="pg-info">/ ${pages} 页（共 ${total} 条）</span>
      <button data-pg="next" ${cur >= pages ? "disabled" : ""}>下一页 ›</button>`;
    holder.querySelector('[data-pg="prev"]').onclick = () => { state[pageKey]--; setupPager(scope, rowSel, perPage, pagerId, pageKey); };
    holder.querySelector('[data-pg="next"]').onclick = () => { state[pageKey]++; setupPager(scope, rowSel, perPage, pagerId, pageKey); };
    const inp = holder.querySelector("[data-pg-input]");
    inp.onchange = () => {
      let v = parseInt(inp.value, 10); if (isNaN(v)) v = 1;
      v = Math.max(1, Math.min(pages, v)); state[pageKey] = v; setupPager(scope, rowSel, perPage, pagerId, pageKey);
    };
    // 分页/筛选导致行数变化后，重算滚动提示（横向/竖向是否还有内容）
    const tbl = sc.querySelector(".qa-table, .kp-table");
    if (tbl) setTimeout(() => tbl.dispatchEvent(new Event("scroll")), 0);
  }
  // 筛选/数据变化后刷新所有可见表格的分页（覆盖主视图与全屏浮层）
  function refreshPagers() {
    const qaMain = $("#qaContent .qa-table");
    if (qaMain) { setupPager($("#qaContent"), "#qaRows .qa-row", 15, "qaPager", "qaPage"); }
    const kpMain = $("#docContent .kp-table");
    if (kpMain) { setupPager($("#docContent"), "#docContent .kp-tr", 15, "kpPager", "kpPage"); }
    const qaFs = $(".qa-fullscreen .qa-table");
    if (qaFs) { setupPager($(".qa-fullscreen"), ".qa-fullscreen .qa-row", 15, "qaFsPager", "qaPage"); }
    const kpFs = $(".kp-fullscreen .kp-table");
    if (kpFs) { setupPager($(".kp-fullscreen"), ".kp-fullscreen .kp-tr", 15, "kpFsPager", "kpPage"); }
  }

  // 从文件导入问答对（含质量门禁审核）
  function openQaFileImport() {
    const inp = document.createElement("input");
    inp.type = "file"; inp.accept = ".json,.csv,.txt"; inp.multiple = true;
    inp.onchange = () => {
      const docId = currentQaDoc(); const d = DOCS[docId];
      if (!d) { toast("请先选择目标问答对集"); return; }
      let pending = inp.files.length, allResults = [];
      [...inp.files].forEach(file => {
        const reader = new FileReader();
        reader.onload = () => {
          const text = reader.result || "";
          const items = parseQaFile(file.name, text);
          // 质量门禁：逐条审核
          items.forEach(it => {
            const ok = gateReview(it);
            it.review = ok ? "已通过" : "已驳回";
            it.evidence = it.evidence || "—";
            it.src = it.src || "上传文件";
            it._gate = ok;
            d.qa.push(it);
          });
          allResults = allResults.concat(items);
          if (--pending === 0) {
            showLib("qa");
            showGateResult(allResults);
          }
        };
        reader.readAsText(file);
      });
      if (inp.files.length === 0) toast("未选择文件");
    };
    inp.click();
  }

  // 质量门禁审核结果显式展示
  function showGateResult(items) {
    if (!items.length) { toast("无可审核的问答对"); return; }
    const pass = items.filter(i => i._gate).length;
    const rej = items.length - pass;
    const pop = document.createElement("div");
    pop.className = "ctx-popup gate-result";
    pop.innerHTML = `<div class="gate-h"><i data-lucide="shield-check"></i><b>质量门禁审核结果</b></div>
      <div class="gate-sum"><span class="gate-pass">${pass} 通过</span><span class="gate-rej">${rej} 驳回</span><span class="gate-total">共 ${items.length} 条</span></div>
      <div class="gate-list">${items.map(i => `<div class="gate-item ${i._gate ? "ok" : "bad"}"><span class="gi-tag">${i._gate ? "通过" : "驳回"}</span><div class="gi-q">${i.q || "（空问题）"}</div></div>`).join("")}</div>
      <button class="btn primary sm gate-close">知道了</button>`;
    document.body.appendChild(pop);
    icons();
    pop.querySelector(".gate-close").onclick = () => pop.remove();
    const cf = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", cf); } };
    setTimeout(() => document.addEventListener("click", cf), 0);
  }
  function parseQaFile(name, text) {
    const ext = name.split(".").pop().toLowerCase();
    try {
      if (ext === "json") {
        const obj = JSON.parse(text);
        const arr = Array.isArray(obj) ? obj : (obj.qa || obj.questions || []);
        return arr.map((x, i) => ({ id: "Q-" + Date.now() % 100000 + "-" + i, q: x.q || x.question || "", a: x.a || x.answer || "", diff: ["简单", "中等", "难"].includes(x.diff) ? x.diff : "中等", evidence: x.evidence || x.ev || "", src: x.src || x.source || "上传文件" }));
      }
      if (ext === "csv" || ext === "txt") {
        return text.split(/\n+/).map((line, i) => {
          const [q, a, diff, evidence, src] = line.split("|");
          return { id: "Q-" + Date.now() % 100000 + "-" + i, q: (q || "").trim(), a: (a || "").trim(), diff: ["简单", "中等", "难"].includes((diff || "").trim()) ? (diff || "").trim() : "中等", evidence: (evidence || "").trim(), src: (src || "上传文件").trim() };
        }).filter(x => x.q);
      }
    } catch (e) { return []; }
    return [];
  }
  // 质量门禁规则（后端审核的显式表现）：问题/答案不可为空、答案长度充足、含关键证据
  function gateReview(it) {
    if (!it.q || !it.a) return false;
    if (it.a.length < 8) return false;
    if (!it.evidence || it.evidence === "—") return false;
    return true;
  }
  function exportQaSet(docId) {
    const d = DOCS[docId]; if (!d) return;
    exportQaRows(d.qa, d.name);
  }
  // 导出一组问答对（支持文件夹聚合/整库导出）
  // 格式：CSV（Excel 友好，列：问题|答案|难度|证据|来源文档，与「新增问答对模板」一致）
  // 导出的 CSV 可直接再次上传到「输入文档库」→ 走 EIU 抽取（每行一条，问题列即 EIU）→ 再生成/泛化，形成闭环
  function exportQaRows(rows, name) {
    if (!rows || !rows.length) { toast("当前没有可导出的问答对"); return; }
    const head = ["问题", "答案", "难度", "证据", "来源文档"];
    const esc = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
    const lines = [head.map(esc).join(",")];
    rows.forEach(q => lines.push([q.q, q.a, q.diff, q.evidence, q.src].map(esc).join(",")));
    const csv = "\ufeff" + lines.join("\r\n"); // BOM：Excel 直接打开不乱码
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = (name || "问答对集").replace(/[\\/:*?"<>|]/g, "_") + "_问答对.csv";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast(`已导出「${name}」的 ${rows.length} 条问答对（CSV，可直接再上传走 EIU 流程）`);
  }
  // 新增问答对模板（CSV，列：问题|答案|难度|证据|来源文档）
  function downloadQaTemplate() {
    const header = "问题|答案|难度|证据|来源文档\n";
    const sample = "示例：请在此填写问题？|示例：请在此填写对应答案。|简单|示例：原始文档中的证据语句。|示例文档.pdf（第一篇 / 第1节）\n";
    const blob = new Blob([header + sample], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = "新增问答对模板.csv";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast("已下载新增问答对模板（CSV），请用「新增单个问答对」旁的「从文件导入」上传");
  }

  function kpFolderHTML(node, all) {
    if (!all.length) return `<div class="lib-head"><div class="lh-ic"><i data-lucide="folder-open"></i></div><div><div class="lh-title">${node.name}</div><div class="lh-sub">知识点</div></div></div>` + emptyState("该目录下无知识点", "已执行拒答验证：目录下文档无可提取知识点。");
    return `<div class="lib-head"><div class="lh-ic"><i data-lucide="list-checks"></i></div><div><div class="lh-title">${node.name}</div><div class="lh-sub">知识点 · ${all.length} 条</div></div>
        <div class="lib-actions"><button class="btn ghost sm" id="kpFolderFullscreenBtn"><i data-lucide="maximize"></i>放大查看</button></div></div>
      <div class="card card-pad">
        ${kpTableHTML(all)}
      </div>`;
  }
  function qaHead(docId) {
    const d = DOCS[docId];
    return `<div class="lib-head"><div class="lh-ic"><i data-lucide="message-square-text"></i></div>
      <div><div class="lh-title">${d.name}</div><div class="lh-sub">问答对 · ${(d.qa || []).length} 条 · 覆盖知识点 ${(d.kp || []).length} 条</div></div></div>`;
  }
  function qaFolderHead(node, all) {
    return `<div class="lib-head"><div class="lh-ic"><i data-lucide="folder-open"></i></div>
      <div><div class="lh-title">${node.name}</div><div class="lh-sub">问答对 · ${all.length} 条</div></div></div>`;
  }

  function renderFolderContent(mode, node) {
    if (!node) { renderLibContent(mode, state.sel[mode]); return; }
    state.folderSel[mode] = node.name;
    if (mode === "doc") {
      $("#docContent").innerHTML = folderDocGridHTML(node);
      $$("#docContent .doc-card").forEach(c => c.onclick = () => {
        const id = c.dataset.doc;
        const tr = $(`#docTree .tree-row[data-doc="${id}"]`);
        if (tr) { $$("#docTree .tree-row.active").forEach(x => x.classList.remove("active")); tr.classList.add("active"); }
        state.sel.doc = id; renderLibContent("doc", id);
      });
    } else {
      const ids = descendantDocs(node); const all = ids.flatMap(i => DOCS[i].qa || []);
      const slug = "agg-" + node.name.replace(/\W/g, "");
      $("#qaContent").innerHTML = (all.length ? qaFolderHead(node, all) + qaBlockHTML(all, "qaChart-" + slug) : qaFolderHead(node, all) + emptyState("该目录下无问答对", "已执行拒答验证：目录下未生成问答对（不单独成栏）。"));
      if (all.length) qaBind("qaChart-" + slug);
    }
    icons();
  }

  function showLib(mode) {
    if (state.folderSel[mode]) renderFolderContent(mode, findNode(state.folderSel[mode]));
    else renderLibContent(mode, state.sel[mode]);
  }

