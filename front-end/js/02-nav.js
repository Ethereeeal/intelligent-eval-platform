  /* ---- 问答对生成：选项随来源类型动态渲染 ---- */
  const UPLOAD_DIR = "uploadTargetDir"; // sessionKey for picked upload dir

  /* ---------------- 五大栏目 ---------------- */
  const NAV = [
    { view: "overview", label: "概览", icon: "layout-dashboard" },
    { view: "studio", label: "问答对生成", icon: "wand-2", badge: { unread: true } },
    { view: "doclib", label: "输入文档库", icon: "folder-open" },
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
      const pur = DOC_PURPOSE[node.doc];
      const purBadge = pur ? `<span class="doc-pur ${pur}">${pur === "gen" ? "泛化问题" : "基础问题"}</span>` : "";
      return `<div class="tree-row" data-doc="${node.doc}" data-name="${node.name}"><i data-lucide="file-text" class="tw-ic"></i><span class="tw-name">${node.name}</span>${purBadge}<button class="tree-dots" data-doc="${node.doc}" data-name="${node.name}" title="更多操作"><i data-lucide="more-horizontal"></i></button></div>`;
    }
    const purBadge = node.purpose ? `<span class="dir-pur ${node.purpose}">${node.purpose === "gen" ? "泛化问题输入" : "基础问题输入"}</span>` : "";
    const desc = node.desc ? `<div class="dir-desc">${node.desc}</div>` : "";
    const sys = node.system ? ` data-system="1" title="系统目录，不可删除或移动"` : "";
    const lockIc = node.system ? `<i data-lucide="lock" class="tw-lock" title="系统目录，不可删除或移动"></i>` : "";
    const dots = node.system ? "" : `<button class="tree-dots" data-folder="1" data-name="${node.name}" title="更多操作"><i data-lucide="more-horizontal"></i></button>`;
    return `<div class="tree-node">
      <div class="tree-row"${sys} data-folder="1" data-name="${node.name}"><i data-lucide="folder" class="tw-ic"></i><span class="tw-name">${node.name}</span>${purBadge}${lockIc}<span class="tw-count">${countDocs(node)}</span><i data-lucide="chevron-down" class="tw-chev"></i>${dots}</div>
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
    const docHint = `<div class="lib-hint"><i data-lucide="info"></i><div><b>输入文档库分为两类用途：</b><span class="hint-basic">基础问题输入文档</span>需经知识点抽取生成基础问答对，<span class="hint-gen">仅泛化输入文档</span>本身即问答对、直接作为泛化问答对输入。</div></div>`;
    const body = (mode === "doc" ? docHint : "") + TREE.children.map(treeNodeHTML).join("");
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
    const isSystem = !!btn.dataset.system;
    const name = btn.dataset.name || "";
    const docId = btn.dataset.doc || "";
    const pop = document.createElement("div");
    pop.className = "ctx-popup";
    // 系统目录不可删除/重命名/新建子文件夹，仅允许「上传文档到此目录」
    const folderMenu = isSystem
      ? `<button data-act="ctx-upload-here">上传文档到此目录</button>`
      : `<button data-act="ctx-newfolder">新建文件夹</button><button data-act="ctx-upload-here">上传文档到此目录</button><button data-act="ctx-rename">重命名</button><button data-act="ctx-delete">删除</button>`;
    pop.innerHTML = isFolder ? folderMenu
      : `<button data-act="ctx-export">导出文档</button><button data-act="ctx-reupload">重新上传</button><button data-act="ctx-upload-here">上传文档</button>`;
    const rect = btn.getBoundingClientRect();
    pop.style.top = rect.bottom + 4 + "px";
    pop.style.left = Math.min(rect.left, window.innerWidth - 180) + "px";
    document.body.appendChild(pop);
    pop.querySelectorAll("button").forEach(b => {
      b.onclick = () => {
        pop.remove();
        if (b.dataset.act === "ctx-export") {
          if (docId && DOCS[docId]) downloadEIU(docId);
        } else if (b.dataset.act === "ctx-newfolder") {
          createFolderInline(container, mode, name);
        } else if (b.dataset.act === "ctx-rename") {
          renameFolderInline(container, mode, name);
        } else if (b.dataset.act === "ctx-delete") {
          deleteFolder(name);
          renderLib(mode);
        } else if (b.dataset.act === "ctx-upload-here") {
          setUploadTarget(isFolder ? name : findNodeParent(name));
          $("#uploadInput").click();
        } else if (b.dataset.act === "ctx-reupload") {
          // 重新上传：文件夹则上传到自身，文档则上传到父目录
          if (isFolder) {
            setUploadTarget(name);
          } else {
            const parentName = findNodeParent(name);
            setUploadTarget(parentName);
          }
          $("#uploadInput").click();
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
            return (pName === "全部文档") ? "本地上传" : pName;
          }
          const r = search(c, [...path, c]);
          if (r) return r;
        }
      }
      return null;
    }
    return search(TREE, []) || "本地上传";
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

  // 将文档移动到目标文件夹（targetPath 为完整路径，含系统目录根，如「基础问题输入文档/子A」）
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
      const parts = path.split("/").filter(Boolean);
      let cur = nodes.find(n => n.name === parts[0]);
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
    const rootName = targetPath.split("/")[0];
    const purpose = rootName === "仅泛化输入文档" ? "gen" : "basic";
    try {
      const res = await fetch(API_BASE + `/api/documents/${docIdNum}/move`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ folder_path: targetPath, purpose })
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

  // 从文档库 tree-row 的 DOM 结构向上回溯得到完整路径（含系统目录根）
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

  // 在指定父目录下内联新建文件夹
  function createFolderInline(container, mode, parentName) {
    const parent = findOrCreateFolder(parentName === "全部文档" ? "" : parentName);
    const node = { name: "新建文件夹", children: [] };
    parent.children.push(node);
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
    const commit = () => {
      const v = input.value.trim();
      if (v && v !== oldName && !nodeListNames(node).includes(v)) node.name = v;
      renderLib(mode);
    };
    input.addEventListener("keydown", e => { if (e.key === "Enter") commit(); if (e.key === "Escape") renderLib(mode); });
    input.addEventListener("blur", commit);
  }

  function nodeListNames(node) {
    return (node.children || []).filter(n => !n.doc).map(n => n.name);
  }

  // 删除文件夹（连同其下文档），并清理 state 引用
  function deleteFolder(name) {
    function removeFrom(nodes) {
      const idx = nodes.findIndex(n => n.name === name);
      if (idx >= 0) {
        const removed = nodes[idx];
        collectDocIds(removed).forEach(id => { delete DOCS[id]; });
        nodes.splice(idx, 1);
        return true;
      }
      for (const n of nodes) if (n.children && removeFrom(n.children)) return true;
      return false;
    }
    removeFrom(TREE.children);
    // 清理选中态
    if (state.sel.doc && !DOCS[state.sel.doc]) state.sel.doc = null;
    if (state.folderSel.doc === name) state.folderSel.doc = null;
    toast(`已删除文件夹「${name}」`);
  }

  function collectDocIds(node) {
    let ids = [];
    if (node.doc) ids.push(node.doc);
    if (node.children) node.children.forEach(c => ids = ids.concat(collectDocIds(c)));
    return ids;
  }

  function setUploadTarget(v) {
    // 上传目标：basic=基础问题输入文档，gen=仅泛化输入文档（系统目录，不可删除/移动）
    // 入参可为 purpose("basic"/"gen")，或系统目录名（"基础问题输入文档"/"仅泛化输入文档"），或任意子路径（含 /）
    const s = String(v || "");
    if (s.includes("/")) {
      state._uploadFolderPath = s;
      state._uploadPurpose = s.startsWith("仅泛化") ? "gen" : "basic";
    } else {
      state._uploadPurpose = (s === "gen" || s.includes("泛化")) ? "gen" : "basic";
    }
  }

  // 上传目录选择器内的树状层级渲染（复用 TREE 结构，仅系统目录可点选）
  function uploadTreeHTML(nodes) {
    return (nodes || []).map(node => {
      const hasChildren = node.children && node.children.length;
      const isSystem = !!node.system;
      const purBadge = node.purpose
        ? `<span class="dir-pur ${node.purpose}">${node.purpose === "gen" ? "泛化问题输入" : "基础问题输入"}</span>`
        : "";
      const lockIc = isSystem ? `<i data-lucide="lock" class="tw-lock" title="系统目录，不可删除或移动"></i>` : "";
      const chev = hasChildren ? `<i data-lucide="chevron-down" class="tw-chev"></i>` : "";
      const childHTML = hasChildren ? `<div class="up-children">${uploadTreeHTML(node.children)}</div>` : "";
      const isDoc = !!node.doc;
      return `<div class="up-node-wrap${hasChildren ? "" : " leaf"}">
        <div class="up-node tree-row" data-folder="1" data-system="${isSystem ? 1 : 0}" data-purpose="${node.purpose || ""}" data-name="${node.name}"${isDoc ? ' data-doc="1"' : ""}>
          <i data-lucide="${isDoc ? "file-text" : "folder"}" class="tw-ic"></i><span class="tw-name">${node.name}</span>${purBadge}${lockIc}${chev}
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

