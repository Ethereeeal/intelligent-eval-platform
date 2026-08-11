  /* ---- 问答对生成：选项随来源类型动态渲染 ---- */
  const UPLOAD_DIR = "uploadTargetDir"; // sessionKey for picked upload dir

  /* ---------------- 五大栏目 ---------------- */
  const NAV = [
    { view: "overview", label: "概览", icon: "layout-dashboard" },
    { view: "doclib", label: "输入文档库", icon: "folder-open" },
    { view: "studio", label: "问答对生成", icon: "wand-2", badge: { unread: true } },
    { view: "qalib", label: "输出问答对库", icon: "message-square-text", badge: { unread: true } }
  ];

  // 未读计数：表示「刚生成完成、用户尚未点进去查看」的问答对集数量。
  // 起始为真实数据里有问答对的文档数；点击进入对应栏目后即标为已读（清零）。
  function unreadCount(view) {
    if (view === "studio" || view === "qalib") {
      return Object.keys(DOCS).filter(id => (DOCS[id].qa || []).length > 0).length;
    }
    return 0;
  }

  function renderNav() {
    $("#nav").innerHTML = NAV.map(n => `
      <div class="nav-item ${n.view === state.view ? "active" : ""}" data-view="${n.view}">
        <i data-lucide="${n.icon}"></i><span>${n.label}</span>
        ${(n.badge && n.badge.unread) ? `<span class="nav-badge unread">${unreadCount(n.view)}</span>` : ""}
      </div>`).join("");
    icons();
  }

  function goto(view) {
    state.view = view;
    $$(".view").forEach(v => v.hidden = v.dataset.view !== view);
    const n = NAV.find(x => x.view === view);
    const crumbEl = $("#crumb"); if (crumbEl) crumbEl.textContent = n ? n.label : "";
    $$("#nav .nav-item").forEach(el => el.classList.toggle("active", el.dataset.view === view));
    // 提醒点：点击即已读（变白）
    if (n && n.badge) { n.badge.unread = false; renderNav(); syncBell(); }
    if (view === "doclib") renderLib("doc");
    if (view === "qalib") renderLib("qa");
    if (view === "studio") renderSrcList(); // 每次进入「问答对生成」都按最新 TREE 刷新源文件树
  }

  function syncBell() {
    const bellText = $("#bellCount");
    if (!bellText) return;
    const sum = NAV.filter(n => n.badge && n.badge.unread)
      .reduce((s, n) => s + unreadCount(n.view), 0);
    bellText.textContent = sum || "";
    bellText.style.display = sum ? "" : "none";
  }

  /* ---------------- 目录树（左竖列，无标题） ---------------- */
  function countDocs(node) {
    if (node.doc) return 1;
    return (node.children || []).reduce((s, c) => s + countDocs(c), 0);
  }
  function descendantDocs(node) {
    if (node.doc) return [node.doc];
    return (node.children || []).flatMap(descendantDocs);
  }
  function findNode(name, node = TREE) {
    if (node.name === name) return node;
    if (node.children) for (const c of node.children) { const r = findNode(name, c); if (r) return r; }
    return null;
  }

  function treeNodeHTML(node) {
    if (node.doc) {
      return `<div class="tree-row" data-doc="${node.doc}" data-name="${node.name}"><i data-lucide="file-text" class="tw-ic"></i><span class="tw-name">${node.name}</span><button class="tree-dots" data-doc="${node.doc}" data-name="${node.name}" title="更多操作"><i data-lucide="more-horizontal"></i></button></div>`;
    }
    // 统一目录：所有文件夹（含根「文档库」）都支持新建子文件夹 / 上传 / 重命名 / 删除
    const isRoot = node === TREE;
    const rootAttr = isRoot ? ` data-root="1"` : "";
    const desc = node.desc ? `<div class="dir-desc">${node.desc}</div>` : "";
    const dots = `<button class="tree-dots" data-folder="1"${rootAttr} data-name="${node.name}" title="更多操作"><i data-lucide="more-horizontal"></i></button>`;
    return `<div class="tree-node">
      <div class="tree-row" data-folder="1"${rootAttr} data-name="${node.name}"><i data-lucide="folder" class="tw-ic"></i><span class="tw-name">${node.name}</span><span class="tw-count">${countDocs(node)}</span><i data-lucide="chevron-down" class="tw-chev"></i>${dots}</div>
      ${desc}
      <div class="tree-children open">${node.children.map(treeNodeHTML).join("")}</div>
    </div>`;
  }

  // 渲染目录树：保留固定的目录头部（tree-bar），仅更新其后内容
  function syncTreeBody(container, bodyHTML) {
    const bar = container.querySelector(":scope > .tree-bar");
    if (bar) {
      let body = container.querySelector(":scope > .tree-body");
      if (!body) { body = document.createElement("div"); body.className = "tree-body"; container.appendChild(body); }
      body.innerHTML = bodyHTML;
      // 将 body 移到 bar 之后（确保顺序）
      if (body.previousElementSibling !== bar) container.insertBefore(body, bar.nextSibling);
    } else {
      container.innerHTML = bodyHTML;
    }
  }

  function bindTree(container, mode) {
    const docHint = `<div class="lib-hint"><i data-lucide="info"></i><div><b>文档库</b>：全部输入文档统一存放于此，可自由新建文件夹/子目录组织；上传后自动解析分块并抽取知识点。</div></div>`;
    const body = (mode === "doc" ? docHint : "") + treeNodeHTML(TREE);
    syncTreeBody(container, body);
    icons();
    container.querySelectorAll(".tree-row").forEach(row => {
      if (row.dataset.folder) {
        row.addEventListener("click", (e) => {
          if (e.target.closest(".tree-dots")) return;
          const kids = row.closest(".tree-node").querySelector(".tree-children");
          if (kids) kids.classList.toggle("open");
          row.classList.toggle("collapsed");
          renderFolderContent(mode, findNode(row.dataset.name));
        });
        // 拖拽上传 / 文档移动到此目录
        if (mode === "doc") {
          row.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); row.classList.add("drop-target"); });
          row.addEventListener("dragleave", (e) => { if (!row.contains(e.relatedTarget)) row.classList.remove("drop-target"); });
          row.addEventListener("drop", (e) => {
            e.preventDefault(); e.stopPropagation();
            row.classList.remove("drop-target");
            const movedDoc = e.dataTransfer && e.dataTransfer.getData("text/doc-id");
            const files = e.dataTransfer && e.dataTransfer.files;
            const targetPath = domPathOf(row);
            if (movedDoc) {
              moveDocToFolder(movedDoc, targetPath);
            } else if (files && files.length) {
              setUploadTarget(targetPath);
              [...files].forEach(f => handleUpload(f, targetPath));
            }
          });
        }
      } else if (row.dataset.doc) {
        row.addEventListener("click", (e) => {
          if (e.target.closest(".tree-dots")) return;
          container.querySelectorAll(".tree-row.active").forEach(r => r.classList.remove("active"));
          row.classList.add("active");
          state.sel[mode] = row.dataset.doc;
          renderLibContent(mode, row.dataset.doc);
        });
        // 支持将文档拖拽到其它文件夹（仅输入文档库）
        if (mode === "doc") {
          row.setAttribute("draggable", "true");
          row.addEventListener("dragstart", (e) => {
            e.dataTransfer.setData("text/doc-id", row.dataset.doc);
            e.dataTransfer.effectAllowed = "move";
          });
        }
      }
    });
    // 三点菜单事件（事件委托，稳健）
    container.addEventListener("click", (e) => {
      const btn = e.target.closest(".tree-dots");
      if (!btn) return;
      e.stopPropagation();
      showTreeContextMenu(e, btn, container, mode);
    });
    // 默认选中第一个文档
    const first = container.querySelector('.tree-row[data-doc]');
    if (first) { first.classList.add("active"); state.sel[mode] = first.dataset.doc; }
  }

  function showTreeContextMenu(e, btn, container, mode) {
    // 关闭已有菜单
    $$(".ctx-popup").forEach(p => p.remove());
    const isFolder = !!btn.dataset.folder;
    const isRoot = !!btn.dataset.root;
    const name = btn.dataset.name || "";
    const docId = btn.dataset.doc || "";
    const pop = document.createElement("div");
    pop.className = "ctx-popup";
    // 根「文档库」不可删除/重命名，但可新建子文件夹与上传；子文件夹全部可操作
    const folderMenu = isRoot
      ? `<button data-act="ctx-newfolder">新建文件夹</button><button data-act="ctx-upload-here">上传文档到此目录</button>`
      : `<button data-act="ctx-newfolder">新建文件夹</button><button data-act="ctx-upload-here">上传文档到此目录</button><button data-act="ctx-rename">重命名</button><button data-act="ctx-delete">删除</button>`;
    pop.innerHTML = isFolder ? folderMenu
      : `<button data-act="ctx-export">导出文档</button><button data-act="ctx-move">移动到</button><button data-act="ctx-rename-doc">重命名</button><button data-act="ctx-delete-doc">删除文档</button>`;
    const rect = btn.getBoundingClientRect();
    pop.style.top = rect.bottom + 4 + "px";
    pop.style.left = Math.min(rect.left, window.innerWidth - 180) + "px";
    document.body.appendChild(pop);
    pop.querySelectorAll("button").forEach(b => {
      b.onclick = async () => {
        pop.remove();
        if (b.dataset.act === "ctx-export") {
          if (docId && DOCS[docId]) downloadEIU(docId);
        } else if (b.dataset.act === "ctx-newfolder") {
          await createFolderInline(container, mode, name);
        } else if (b.dataset.act === "ctx-rename") {
          renameFolderInline(container, mode, name);
        } else if (b.dataset.act === "ctx-delete") {
          await deleteFolder(name);
          renderLib(mode);
        } else if (b.dataset.act === "ctx-upload-here") {
          // 上传到此目录：用完整路径（含根「文档库」），根上传传空
          const targetNode = isFolder ? findNode(name) : findNode(findNodeParent(name));
          setUploadTarget(targetNode ? fullFolderPathOf(targetNode) : "");
          $("#uploadInput").click();
        } else if (b.dataset.act === "ctx-move") {
          // 移动到…：弹出「文档库」目录选择器，选择目标文件夹后移动文档
          showMoveDocModal(docId);
        } else if (b.dataset.act === "ctx-rename-doc") {
          // 重命名文档：内联改名，仅更新显示名（不影响落盘文件与问答对）
          renameDocInline(container, mode, docId, name);
        } else if (b.dataset.act === "ctx-delete-doc") {
          // 删除文档：连带删除知识点（EIU），但保留问答对库中已生成的问题
          await deleteDoc(docId, name);
          renderLib(mode);
        }
      };
    });
    const closeCtx = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", closeCtx); } };
    setTimeout(() => document.addEventListener("click", closeCtx), 0);
  }

  function findNodeParent(childName) {
    function search(node, path) {
      if (node.children) {
        for (const c of node.children) {
          if (c.name === childName) {
            const pName = path.length ? path[path.length - 1].name : node.name;
            return (pName === TREE.name) ? "" : pName;
          }
          const r = search(c, [...path, c]);
          if (r) return r;
        }
      }
      return null;
    }
    return search(TREE, []) || "";
  }

  // 文件夹完整路径（用 / 连接），用于拖拽时确定上传目标
  function folderPathOf(folderName) {
    function search(node, prefix) {
      if (node.children) {
        for (const c of node.children) {
          const path = prefix ? prefix + "/" + c.name : c.name;
          if (c.name === folderName) return path;
          const r = search(c, path);
          if (r) return r;
        }
      }
      return null;
    }
    const p = search(TREE, "");
    return p || folderName;
  }

  // 将文档移动到目标文件夹（targetPath 为完整路径，含根「文档库」，如「文档库/子A」）
  async function moveDocToFolder(docId, targetPath) {
    function findDocNode(id, nodes) {
      for (const n of nodes) {
        if (n.doc === id) return n;
        if (n.children) { const r = findDocNode(id, n.children); if (r) return r; }
      }
      return null;
    }
    function removeDocNode(id, nodes) {
      const i = nodes.findIndex(n => n.doc === id);
      if (i >= 0) return nodes.splice(i, 1)[0];
      for (const n of nodes) if (n.children) { const r = removeDocNode(id, n.children); if (r) return r; }
      return null;
    }
    function findFolderByPath(path, nodes) {
      const parts = path.split("/").filter(Boolean).filter(p => p !== TREE.name);
      if (!parts.length) return TREE; // 目标为根「文档库」
      let cur = nodes.find(n => n.name === parts[0] && !n.doc);
      if (!cur) return null;
      for (let i = 1; i < parts.length; i++) {
        const next = cur.children && cur.children.find(n => n.name === parts[i] && !n.doc);
        if (!next) return null;
        cur = next;
      }
      return cur;
    }
    if (!TREE.children || !targetPath) return;
    const docNode = findDocNode(docId, TREE.children);
    const target = findFolderByPath(targetPath, TREE.children);
    if (!docNode || !target) return;
    if (docNode === target || target.children.includes(docNode)) { toast("已在目标目录"); return; }
    const docIdNum = String(docId).replace(/^doc/, "");
    const purpose = "basic"; // 统一基础问题输入，是否泛化由生成界面决定
    // 存相对文档库根的子路径（如「子A/子B」），空串表示文档库根
    const relPath = targetPath.split("/").filter(p => p && p !== TREE.name).join("/");
    // 后端 move_document 接收表单参数（Form），方法为 PATCH
    // folder_path 始终传值：空串表示「文档库」根（后端 update_document 以 None 表示不更新，
    // 若省略则移回根目录时旧目录不会被清掉）
    const fd = new FormData();
    fd.append("folder_path", relPath);
    fd.append("purpose", purpose);
    try {
      const res = await fetch(API_BASE + `/api/documents/${docIdNum}/move`, {
        method: "PATCH",
        body: fd
      });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast(`移动失败：${err.detail || res.status}`, "warn");
        return;
      }
    } catch (e) {
      toast("移动请求失败，请检查后端", "warn");
      return;
    }
    const moved = removeDocNode(docId, TREE.children);
    if (!moved) return;
    target.children.push(moved);
    renderLib("doc");
    toast(`已将「${moved.name}」移动到「${targetPath}」`);
    icons();
  }

  // 「移动到…」：弹出「文档库」目录选择器，选中目标文件夹后移动文档
  function showMoveDocModal(docId) {
    $$(".ctx-popup").forEach(p => p.remove());
    const mask = document.createElement("div");
    mask.className = "up-modal-mask";
    mask.innerHTML = `<div class="up-modal">` +
      `<div class="up-modal-head"><span>移动文档到目标目录</span>` +
      `<button class="up-close" title="关闭">×</button></div>` +
      `<div class="up-modal-body"><div class="up-tree">${uploadTreeHTML([TREE])}</div></div>` +
      `<div class="up-modal-foot"><button class="up-confirm">移动到此处</button></div>` +
      `<div class="up-hint">选择「文档库」内的目标文件夹，将文档移动到该目录；拖拽文档到左侧目录树同样可以移动。</div>` +
      `</div>`;
    document.body.appendChild(mask);
    if (window.lucide) window.lucide.createIcons();
    const closeModal = () => mask.remove();
    mask.querySelector(".up-close").onclick = closeModal;
    mask.addEventListener("click", (e) => { if (e.target === mask) closeModal(); });
    let targetPath = "";
    // 目录树：点击任意文件夹节点即选中为目标（含根「文档库」）；文档节点忽略；可展开/折叠
    mask.querySelectorAll(".up-node").forEach(row => {
      row.addEventListener("click", (e) => {
        e.stopPropagation();
        if (row.dataset.doc) return; // 文档不可作为移动目标
        row.parentElement.classList.toggle("collapsed");
        mask.querySelectorAll(".up-node").forEach(r => r.classList.remove("sel"));
        row.classList.add("sel");
        targetPath = fullFolderPathOf(row.__node);
      });
    });
    bindTreeNodes(mask.querySelector(".up-tree"), [TREE]);
    mask.querySelector(".up-confirm").onclick = () => {
      if (!targetPath) { toast("请先选择目标目录", "warn"); return; }
      closeModal();
      moveDocToFolder(docId, targetPath);
    };
  }

  // 从文档库 tree-row 的 DOM 结构向上回溯得到完整路径（含根「文档库」，用 / 连接）
  function domPathOf(row) {
    const names = [];
    let cur = row;
    while (cur && cur.dataset && cur.dataset.name) {
      names.unshift(cur.dataset.name);
      const node = cur.closest(".tree-node");
      const parentChildren = node ? node.parentElement : null;
      const parentNode = parentChildren ? parentChildren.closest(".tree-node") : null;
      cur = parentNode ? parentNode.querySelector(":scope > .tree-row") : null;
    }
    return names.join("/");
  }

  // 在指定父目录下内联新建文件夹（持久化到后端 folder 表，刷新后仍保留）
  async function createFolderInline(container, mode, parentName) {
    // 根「文档库」直接作为父节点；子文件夹按其名字查找（已存在）作为父节点
    const parent = (parentName === TREE.name) ? TREE : (findOrCreateFolder(parentName) || TREE);
    const parentRel = relPathOfNode(parent);
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
      parent.children.push({ name: created.name, children: [], folderId: created.folder_id });
    } catch (e) {
      toast("新建文件夹请求失败，请检查后端", "warn");
      return;
    }
    renderLib(mode);
    // 选中新文件夹行进入重命名态
    const rows = container.querySelectorAll(".tree-row");
    rows.forEach(r => { if (r.dataset.name === "新建文件夹" && r.dataset.folder) renameFolderInline(container, mode, "新建文件夹"); });
  }

  // 内联重命名文件夹
  function renameFolderInline(container, mode, oldName) {
    const node = findNode(oldName);
    if (!node) return;
    const treeNode = container.querySelector(`.tree-row[data-name="${CSS.escape(oldName)}"][data-folder]`);
    if (!treeNode) return;
    const nameSpan = treeNode.querySelector(".tw-name");
    const input = document.createElement("input");
    input.type = "text"; input.value = oldName; input.className = "tree-rename-input";
    input.style.cssText = "font-size:12.5px;padding:2px 6px;border:1px solid var(--brand);border-radius:6px;width:120px;outline:none;";
    nameSpan.replaceWith(input);
    input.focus(); input.select();
    const commit = async () => {
      const v = input.value.trim();
      const oldRel = relPathOfNode(node);
      if (v && v !== oldName && !nodeListNames(node).includes(v)) {
        // 原位重命名：新路径 = 父目录相对路径 + "/" + 新名；后端会一并重写文档 folder_path
        const parentNode = findParentOf(node, TREE.children) || TREE;
        const parentRel = relPathOfNode(parentNode);
        const newRel = parentRel ? parentRel + "/" + v : v;
        try {
          const fd = new FormData();
          fd.append("owner", CURRENT_USER);
          fd.append("from_path", oldRel);
          fd.append("to_path", newRel);
          const res = await fetch(API_BASE + "/api/folders/move", { method: "PATCH", body: fd });
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            toast(`重命名失败：${err.detail || res.status}`, "warn");
            renderLib(mode);
            return;
          }
          node.name = v;
        } catch (e) {
          toast("重命名请求失败，请检查后端", "warn");
        }
      }
      renderLib(mode);
    };
    input.addEventListener("keydown", e => { if (e.key === "Enter") commit(); if (e.key === "Escape") renderLib(mode); });
    input.addEventListener("blur", commit);
  }

  function nodeListNames(node) {
    return (node.children || []).filter(n => !n.doc).map(n => n.name);
  }

  // 内联重命名文档：仅更新显示名 file_name，不影响落盘文件与已生成问答对
  function renameDocInline(container, mode, docId, oldName) {
    const node = findDocNodeById(docId, TREE.children);
    if (!node) return;
    const treeRow = container.querySelector(`.tree-row[data-doc="${CSS.escape(docId)}"]`);
    if (!treeRow) return;
    const nameSpan = treeRow.querySelector(".tw-name");
    const input = document.createElement("input");
    input.type = "text"; input.value = oldName; input.className = "tree-rename-input";
    input.style.cssText = "font-size:12.5px;padding:2px 6px;border:1px solid var(--brand);border-radius:6px;width:160px;outline:none;";
    nameSpan.replaceWith(input);
    input.focus(); input.select();
    const commit = async () => {
      const v = input.value.trim();
      if (v && v !== oldName) {
        const docIdNum = String(docId).replace(/^doc/, "");
        try {
          const fd = new FormData();
          fd.append("new_name", v);
          const res = await fetch(API_BASE + `/api/documents/${docIdNum}/rename`, { method: "PATCH", body: fd });
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            toast(`重命名失败：${err.detail || res.status}`, "warn");
            renderLib(mode);
            return;
          }
          node.name = v;
          if (DOCS[docId]) DOCS[docId].name = v;
        } catch (e) {
          toast("重命名请求失败，请检查后端", "warn");
        }
      }
      renderLib(mode);
    };
    input.addEventListener("keydown", e => { if (e.key === "Enter") commit(); if (e.key === "Escape") renderLib(mode); });
    input.addEventListener("blur", commit);
  }

  // 按 docId（如 doc4）在目录树中查找文档节点
  function findDocNodeById(docId, nodes) {
    for (const n of nodes || []) {
      if (n.doc === docId) return n;
      if (n.children) { const r = findDocNodeById(docId, n.children); if (r) return r; }
    }
    return null;
  }

  // 删除文档：两段确认。
  // 第一段：弹窗展示该文档及其关联的问答对库清单，明确提示删除范围；
  // 第二段：用户点击「确认删除」后，后端 DELETE /api/documents/{id}
  // 连带删除 document/blocks/eiu（知识点）/generated_case（问答对）/质检结果。
  // 删除后前端同步：目录树移除节点、DOCS 移除条目、清理选中态。
  function deleteDoc(docId, name) {
    return new Promise(resolve => {
      const d = DOCS[docId];
      const qaList = (d && d.qa) || [];
      const docIdNum = String(docId).replace(/^doc/, "");
      $$(".ctx-popup").forEach(p => p.remove());
      const mask = document.createElement("div");
      mask.className = "up-modal-mask";
      mask.innerHTML = `<div class="up-modal">` +
        `<div class="up-modal-head"><span>删除文档</span>` +
        `<button class="up-close" title="关闭">×</button></div>` +
        `<div class="up-modal-body">` +
        `<p class="del-confirm-txt">确定要删除文档「<b>${escapeHTML(name)}</b>」吗？<br>以下问答对库与该文档相关也会一并删除：</p>` +
        (qaList.length
          ? `<div class="del-qa-list">${qaList.map(q => `<div class="del-qa-item"><span class="del-qa-q">${escapeHTML(q.q)}</span><span class="del-qa-meta">${escapeHTML(q.diff)} · ${escapeHTML(q.review)}</span></div>`).join("")}</div>`
          : `<p class="muted del-none">该文档暂无关联问答对。</p>`) +
        `</div>` +
        `<div class="up-modal-foot"><button class="up-cancel">取消</button><button class="up-confirm up-danger">确认删除</button></div>` +
        `<div class="up-hint">删除后该文档的知识点（EIU）与问答对库中已生成的问题将一并删除，此操作不可恢复。</div>` +
        `</div>`;
      document.body.appendChild(mask);
      if (window.lucide) window.lucide.createIcons();
      const closeModal = () => { mask.remove(); resolve(false); };
      mask.querySelector(".up-close").onclick = closeModal;
      mask.addEventListener("click", (e) => { if (e.target === mask) closeModal(); });
      mask.querySelector(".up-cancel").onclick = closeModal;
      mask.querySelector(".up-confirm").onclick = async () => {
        try {
          const res = await fetch(API_BASE + `/api/documents/${docIdNum}`, { method: "DELETE" });
          if (!res.ok) {
            const err = await res.json().catch(() => ({}));
            toast(`删除失败：${err.detail || res.status}`, "warn");
            mask.remove(); resolve(false); return;
          }
        } catch (e) {
          toast("删除请求失败，请检查后端", "warn");
          mask.remove(); resolve(false); return;
        }
        // 后端已删除文档 + 知识点 + 问答对 + 质检结果；前端同步移除
        removeDocNodeById(docId, TREE.children);
        delete DOCS[docId];
        delete DOC_PURPOSE[docId];
        if (state.sel.doc === docId) state.sel.doc = null;
        if (state.sel.qa === docId) state.sel.qa = null;
        if (state.folderSel.doc === docId) state.folderSel.doc = null;
        // 「问答对生成」已勾选的文件中若含该文档，一并移除
        if (Array.isArray(state.studioSrc)) state.studioSrc = state.studioSrc.filter(x => x !== docId);
        mask.remove();
        toast(`已删除文档「${name}」及其 ${qaList.length} 条问答对`);
        resolve(true);
      };
    });
  }

  // 按 docId 移除目录树中的文档节点
  function removeDocNodeById(docId, nodes) {
    if (!Array.isArray(nodes)) return;
    const i = nodes.findIndex(n => n.doc === docId);
    if (i >= 0) return nodes.splice(i, 1)[0];
    for (const n of nodes) if (n.children) { const r = removeDocNodeById(docId, n.children); if (r) return r; }
    return null;
  }

  // 删除文件夹（持久化到后端）：后端递归删除 folder 记录，其下文档自动上移到父目录，不丢文档
  async function deleteFolder(name) {
    const node = findNode(name);
    if (!node) return;
    const relPath = relPathOfNode(node);
    const parent = findParentOf(node, TREE.children);
    try {
      const res = await fetch(API_BASE + `/api/folders?path=${encodeURIComponent(relPath)}&owner=${CURRENT_USER}`, { method: "DELETE" });
      if (!res.ok) {
        const err = await res.json().catch(() => ({}));
        toast(`删除失败：${err.detail || res.status}`, "warn");
        return;
      }
    } catch (e) {
      toast("删除请求失败，请检查后端", "warn");
      return;
    }
    // 前端同步：文件夹节点移除，其下文档节点上移到父级（DOCS 保留——后端文档已上移）
    const docsUnder = collectDocNodes(node);
    if (parent) {
      parent.children = parent.children.filter(n => n !== node);
      docsUnder.forEach(d => parent.children.push(d));
    }
    // 清理选中态
    if (state.sel.doc && !DOCS[state.sel.doc]) state.sel.doc = null;
    if (state.folderSel.doc === name) state.folderSel.doc = null;
    toast(`已删除文件夹「${name}」` + (docsUnder.length ? `，其中 ${docsUnder.length} 个文档已移至上级目录` : ""));
  }

  // 查找节点在其父 children 中的父节点
  function findParentOf(node, nodes) {
    for (const n of nodes) {
      if (n.children && n.children.includes(node)) return n;
      if (n.children) { const r = findParentOf(node, n.children); if (r) return r; }
    }
    return null;
  }

  // 递归收集文件夹节点下的全部文档节点（不删 DOCS，仅用于上移）
  function collectDocNodes(node) {
    let res = [];
    if (node.doc) res.push(node);
    if (node.children) node.children.forEach(c => res = res.concat(collectDocNodes(c)));
    return res;
  }

  function setUploadTarget(v) {
    // 上传目标：文档库内任意子目录路径（相对文档库根，如「子A/子B」），空 = 文档库根
    state._uploadFolderPath = String(v || "").replace(/^\/+|\/+$/g, "") || "";
    state._uploadPurpose = "basic";
  }

  // 上传目录选择器内的树状层级渲染（复用 TREE 结构，任意文件夹均可选为目标）
  function uploadTreeHTML(nodes) {
    return (nodes || []).map(node => {
      const hasChildren = node.children && node.children.length;
      const chev = hasChildren ? `<i data-lucide="chevron-down" class="tw-chev"></i>` : "";
      const childHTML = hasChildren ? `<div class="up-children">${uploadTreeHTML(node.children)}</div>` : "";
      const isDoc = !!node.doc;
      return `<div class="up-node-wrap${hasChildren ? "" : " leaf"}">
        <div class="up-node tree-row" data-folder="1" data-name="${node.name}"${isDoc ? ' data-doc="1"' : ""}>
          <i data-lucide="${isDoc ? "file-text" : "folder"}" class="tw-ic"></i><span class="tw-name">${node.name}</span>${chev}
        </div>${childHTML}
      </div>`;
    }).join("");
  }

  function flattenFolders() {
    const res = [];
    function walk(nodes, prefix) {
      for (const n of nodes) {
        if (!n.doc) { const path = prefix ? prefix + "/" + n.name : n.name; res.push(path); if (n.children) walk(n.children, path); }
      }
    }
    if (TREE.children) walk(TREE.children, "");
    return res;
  }

