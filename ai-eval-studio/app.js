/* ============================================================
   问答对生成平台 — 交互逻辑
   栏目：概览 / 问答对生成 / 输入文档库 / 输出问答对库
   ============================================================ */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  // 图标渲染：lucide 若未就绪则静默跳过，避免直接抛错阻断后续逻辑
  const icons = () => { if (window.lucide) { try { lucide.createIcons(); } catch (e) {} } };

  /* ---------------- 数据模型 ---------------- */
  const DOCS = {
    d1: {
      name: "授信管理办法.pdf", type: "PDF", size: "12.4 MB", status: "已解析", ver: "v3", updated: "2 分钟前",
      preview: [
        "§2.1 集团客户授信额度不得超过其核心企业上一年度经审计营业收入的 50%。",
        "§2.3 单一客户授信额度上限按前述比例的 30% 执行。",
        "§4.2 逾期 90 天（含）以上计入不良，并启动分类下调流程。"
      ],
      versions: [
        { tag: "v3", note: "当前 · 修订授信比例口径", time: "2 分钟前" },
        { tag: "v2", note: "补充并表口径说明", time: "3 天前" },
        { tag: "v1", note: "首次入库", time: "1 个月前" }
      ],
      kp: [
        { id: "KP-001", stmt: "借款人授信额度测算规则", type: "规则", prio: "必须覆盖", state: "已覆盖", ev: "信贷手册 §3.2" },
        { id: "KP-002", stmt: "单一客户授信比例约束", type: "约束", prio: "必须覆盖", state: "已覆盖", ev: "授信政策 §2.3" },
        { id: "KP-003", stmt: "逾期不良认定约束", type: "约束", prio: "建议覆盖", state: "待补充", ev: "资产质量 §5" }
      ],
      qa: [
        { id: "Q-101", q: "集团客户授信额度的上限如何确定？", a: "不得超过核心企业上一年度经审计营业收入的 50%。", diff: "难", review: "待审核", src: "授信政策 §2.1", evidence: "不得超过核心企业上一年度经审计营业收入的 50%。", type: "gen" },
        { id: "Q-102", q: "单一客户授信额度上限是多少？", a: "按集团客户授信比例的 30% 执行。", diff: "简单", review: "已通过", src: "授信政策 §2.3", evidence: "按集团客户授信比例的 30% 执行。", type: "plain" },
        { id: "Q-103", q: "逾期多少天计入不良？", a: "逾期 90 天（含）以上计入不良。", diff: "简单", review: "已通过", src: "资产质量 §4.2", evidence: "逾期 90 天（含）以上计入不良。", type: "gen" }
      ],
      review: [
        { id: "R-1", q: "集团客户授信额度的上限如何确定？", status: "待审核" },
        { id: "R-2", q: "并表口径下如何计算核心企业收入？", status: "待审核" }
      ]
    },
    d2: {
      name: "五级分类认定.pdf", type: "PDF", size: "4.2 MB", status: "已解析", ver: "v2", updated: "1 小时前",
      preview: [
        "§2 正常类：借款人能够履行合同，没有足够理由怀疑贷款本息不能按时足额偿还。",
        "§4 可疑类：借款人无法足额偿还贷款本息，即使执行担保，也肯定会造成较大损失。"
      ],
      versions: [
        { tag: "v2", note: "当前 · 修订可疑类认定", time: "1 小时前" },
        { tag: "v1", note: "首次入库", time: "2 周前" }
      ],
      kp: [
        { id: "KP-004", stmt: "五级分类认定流程", type: "流程", prio: "必须覆盖", state: "已覆盖", ev: "风险分类 §2" }
      ],
      qa: [
        { id: "Q-201", q: "可疑类贷款如何认定？", a: "无法足额偿还本息，即使执行担保也肯定造成较大损失。", diff: "中等", review: "已通过", src: "风险分类 §4", evidence: "无法足额偿还本息，即使执行担保也肯定造成较大损失。", type: "gen" }
      ],
      review: []
    },
    d3: {
      name: "反欺诈管理办法.pdf", type: "DOCX", size: "3.1 MB", status: "已解析", ver: "v5", updated: "20 分钟前",
      preview: [
        "§5 触发黑名单且金额超阈值，应立即拦截并转入人工复核，记录处置轨迹。",
        "§5.2 设备指纹异常视为高风险，提升核验等级。"
      ],
      versions: [
        { tag: "v5", note: "当前 · 新增设备指纹规则", time: "20 分钟前" },
        { tag: "v4", note: "修订黑名单阈值", time: "2 周前" }
      ],
      kp: [
        { id: "KP-005", stmt: "黑名单拦截规则", type: "规则", prio: "必须覆盖", state: "已覆盖", ev: "反欺诈 §5" },
        { id: "KP-006", stmt: "设备指纹风险评级", type: "规则", prio: "建议覆盖", state: "已覆盖", ev: "反欺诈 §5.2" }
      ],
      qa: [
        { id: "Q-301", q: "触发黑名单且超阈值如何处理？", a: "立即拦截并转入人工复核，记录处置轨迹。", diff: "难", review: "待审核", src: "反欺诈 §5", evidence: "触发黑名单且金额超阈值，应立即拦截并转入人工复核，记录处置轨迹。", type: "gen" },
        { id: "Q-302", q: "设备指纹异常应如何处置？", a: "视为高风险，提升核验等级。", diff: "中等", review: "已通过", src: "反欺诈 §5.2", evidence: "设备指纹异常视为高风险，提升核验等级。", type: "plain" }
      ],
      review: [
        { id: "R-3", q: "触发黑名单且超阈值如何处理？", status: "待审核" }
      ]
    },
    d4: {
      name: "理财适当性规则.pdf", type: "PDF", size: "2.6 MB", status: "已解析", ver: "v1", updated: "3 小时前",
      preview: ["§3 产品风险等级应与客户风险承受能力相匹配。"],
      versions: [{ tag: "v1", note: "首次入库", time: "3 小时前" }],
      kp: [], qa: [], review: []
    },
    d5: {
      name: "风险分类补充规则.pdf", type: "PDF", size: "1.8 MB", status: "已解析", ver: "v1", updated: "昨天",
      // 泛化问题输入文档：本身即问答对，无需抽取知识点
      preview: [
        "Q：逾期贷款如何认定不良？\nA：逾期 90 天（含）以上计入不良，并启动分类下调流程。",
        "Q：正常类贷款认定标准？\nA：借款人能够履行合同，没有足够理由怀疑贷款本息不能按时足额偿还。"
      ],
      versions: [{ tag: "v1", note: "首次入库（泛化问答对）", time: "昨天" }],
      kp: [], qa: [], review: []
    }
  };

  const TREE = {
    name: "全部文档", children: [
      { name: "基础问题输入文档", purpose: "basic", desc: "需经知识点抽取生成基础问答对", children: [
        { name: "信贷政策", children: [
          { name: "授信管理办法.pdf", doc: "d1" },
          { name: "风险分类", children: [
            { name: "五级分类认定.pdf", doc: "d2" }
          ] }
        ] },
        { name: "风险防控", children: [
          { name: "反欺诈管理办法.pdf", doc: "d3" }
        ] },
        { name: "理财业务", children: [
          { name: "理财适当性规则.pdf", doc: "d4" }
        ] }
      ] },
      { name: "泛化问题输入文档", purpose: "gen", desc: "本身即问答对，无需抽取知识点，直接作为泛化问答对输入", children: [
        { name: "风险分类", children: [
          { name: "风险分类补充规则.pdf", doc: "d5" }
        ] }
      ] }
    ]
  };
  // 各文档归属的输入用途（basic=基础问题 gen=泛化问题）
  const DOC_PURPOSE = { d1: "basic", d2: "basic", d3: "basic", d4: "basic", d5: "gen" };

  const state = {
    view: "overview",
    sel: { doc: "d1", kp: "d1", qa: "d1" },
    folderSel: { doc: null, kp: null, qa: null },
    studioType: "doc",
    studioSrc: ["d1"],
    studioOpts: { crossBlock: true, crossDoc: true, difficulties: ["简单","中等","难"], generalizeCount: 3, keepOriginal: true, flatOutput: false }
  };

  const charts = {};

  /* ---- 问答对生成：选项随来源类型动态渲染 ---- */
  const UPLOAD_DIR = "uploadTargetDir"; // sessionKey for picked upload dir

  /* ---------------- 五大栏目 ---------------- */
  const NAV = [
    { view: "overview", label: "概览", icon: "layout-dashboard" },
    { view: "studio", label: "问答对生成", icon: "wand-2", badge: { text: "6", unread: true } },
    { view: "doclib", label: "输入文档库", icon: "folder-open" },
    { view: "qalib", label: "输出问答对库", icon: "message-square-text", badge: { text: "12", unread: true } }
  ];

  function renderNav() {
    $("#nav").innerHTML = NAV.map(n => `
      <div class="nav-item ${n.view === state.view ? "active" : ""}" data-view="${n.view}">
        <i data-lucide="${n.icon}"></i><span>${n.label}</span>
        ${n.badge ? `<span class="nav-badge ${n.badge.unread ? "unread" : "read"}">${n.badge.text}</span>` : ""}
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
      .reduce((s, n) => s + (parseInt(n.badge.text) || 0), 0);
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
    return `<div class="tree-node">
      <div class="tree-row" data-folder="1" data-name="${node.name}"><i data-lucide="folder" class="tw-ic"></i><span class="tw-name">${node.name}</span>${purBadge}<span class="tw-count">${countDocs(node)}</span><i data-lucide="chevron-down" class="tw-chev"></i><button class="tree-dots" data-folder="1" data-name="${node.name}" title="更多操作"><i data-lucide="more-horizontal"></i></button></div>
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
    const docHint = `<div class="lib-hint"><i data-lucide="info"></i><div><b>输入文档库分为两类用途：</b><span class="hint-basic">基础问题输入文档</span>需经知识点抽取生成基础问答对，<span class="hint-gen">泛化问题输入文档</span>本身即问答对、直接作为泛化问答对输入。</div></div>`;
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
            if (movedDoc) {
              moveDocToFolder(movedDoc, row.dataset.name);
            } else if (files && files.length) {
              const path = folderPathOf(row.dataset.name);
              [...files].forEach(f => { setUploadTarget(path); handleUpload(f); });
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
    const name = btn.dataset.name || "";
    const docId = btn.dataset.doc || "";
    const pop = document.createElement("div");
    pop.className = "ctx-popup";
    pop.innerHTML = isFolder
      ? `<button data-act="ctx-newfolder">新建文件夹</button><button data-act="ctx-upload-here">上传文档到此目录</button><button data-act="ctx-rename">重命名</button><button data-act="ctx-delete">删除</button>`
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

  // 将文档移动到目标文件夹（按名称定位，支持同名时取首次出现）
  function moveDocToFolder(docId, targetFolderName) {
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
    function findFolderNode(name, nodes) {
      for (const n of nodes) {
        if (n.name === name && n.children && !n.doc) return n;
        if (n.children) { const r = findFolderNode(name, n.children); if (r) return r; }
      }
      return null;
    }
    if (!TREE.children) return;
    const docNode = findDocNode(docId, TREE.children);
    const target = findFolderNode(targetFolderName, TREE.children);
    if (!docNode || !target) return;
    if (docNode === target || target.children.includes(docNode)) { toast("已在目标目录"); return; }
    const moved = removeDocNode(docId, TREE.children);
    if (!moved) return;
    target.children.push(moved);
    renderLib("doc");
    toast(`已将「${moved.name}」移动到「${targetFolderName}」`);
    icons();
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

  function setUploadTarget(folderName) {
    state._uploadTarget = folderName;
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

  /* ---------------- 库内容渲染 ---------------- */
  function emptyState(title, desc) {
    return `<div class="empty-state"><div class="es-ic"><i data-lucide="shield-question"></i></div>
      <div class="es-t">${title}</div><div class="es-d">${desc}</div></div>`;
  }

  function docContentHTML(docId) {
    const d = DOCS[docId];
    const isGen = DOC_PURPOSE[docId] === "gen";
    const isParsing = d.status.includes("解析中");
    const progressBar = isParsing ? `<div class="upload-prog-wrap mt"><div class="upload-prog-track"><div class="upload-prog-bar" style="width:${Math.round(d.parseProgress||0)}%"></div></div><span class="upload-prog-txt">知识点解析中 ${Math.round(d.parseProgress||0)}%</span></div>` : "";
    return `<div class="lib-head">
        <div class="lh-ic"><i data-lucide="file-text"></i></div>
        <div><div class="lh-title">${d.name}</div><div class="lh-sub">${d.type} · ${d.size} · ${d.status} · ${d.ver} · ${d.updated}</div></div>
        <div class="lib-actions"><button class="btn ghost sm"><i data-lucide="eye"></i>在线查看</button><button class="btn ghost sm"><i data-lucide="history"></i>版本</button><button class="btn ghost sm" id="dlEIUDoc"><i data-lucide="download"></i>导出知识点</button></div>
      </div>
      <div class="card card-pad">
        ${progressBar}
        <div class="sec-h">在线查看</div>
        <div class="doc-preview">${d.preview.length ? d.preview.map(p => `<p>${p}</p>`).join("") : `<p class="muted">知识抽取完成后将显示文档预览</p>`}</div>
        <div class="sec-h mt">版本历史</div>
        <div class="ver-list">${d.versions.map(v => `<div class="ver"><span class="ver-tag">${v.tag}</span><span>${v.note}</span><span class="mut">${v.time}</span></div>`).join("")}</div>
        ${isGen ? `<div class="gen-input-note"><i data-lucide="info"></i><div>本输入文档属于「泛化问题输入文档」，<b>本身即问答对，无需抽取知识点</b>，将直接作为泛化问答对输入使用。</div></div>` : `<div class="sec-h mt">知识点 · ${d.kp.length} 条</div>
        ${d.kp && d.kp.length ? `<div class="kp-list">${d.kp.map(k => `<div class="kp-row"><div class="kp-stmt">${k.stmt}</div><div class="kp-meta"><span class="tag ${k.type === '规则/约束' ? 't-rule' : k.type === '流程' ? 't-flow' : 't-def'}">${k.type}</span><span>${k.prio}</span><span>${k.state}</span><span class="kp-ev">证据 ${k.ev}</span></div></div>`).join("")}</div>` : `<p class="muted mt">${isParsing ? "正在解析中..." : "未识别到可抽取知识点。"}</p>`}`}
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
          <div class="doc-preview">${d.preview.slice(0, 2).map(p => `<p>${p}</p>`).join("")}</div>
        </div>`;
      }).join("")}</div>`;
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
        <div class="lib-actions"><button class="btn ghost sm" id="dlEIUKp"><i data-lucide="download"></i>导出知识点</button></div></div>
      <div class="card card-pad">
        <div class="kp-head"><span>编号</span><span>知识点陈述</span><span>类型</span><span>优先级</span><span>状态</span></div>
        ${d.kp.map(k => `<div class="kp-row">
          <span class="kp-id">${k.id}</span><span class="kp-stmt">${k.stmt}</span>
          <span><span class="pill br">${k.type}</span></span><span class="muted">${k.prio}</span>
          <span><span class="badge ${k.state === "已覆盖" ? "ok" : "warn"}">${k.state}</span></span>
        </div>`).join("")}
        <p class="muted mt">证据定位示例：${d.kp[0].ev}；置信度≥0.9 视为已覆盖。</p>
      </div>`;
  }

  function renderLibContent(mode, docId) {
    state.folderSel[mode] = null;
    if (mode === "doc") {
      $("#docContent").innerHTML = docContentHTML(docId);
      const dl = $("#docContent #dlEIUDoc"); if (dl) dl.onclick = () => downloadEIU(docId);
    } else {
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
    if (mode === "qa") bindQaTree($(treeId)); else bindTree($(treeId), mode);
    renderLibContent(mode, state.sel[mode]);
  }

  // 类型标签：gen=泛化问题 plain=基础问题
  function typeLabel(t) { return t === "gen" ? "泛化问题" : (t === "plain" ? "基础问题" : t); }

  // 输出问答对目录树：两个固定目录（泛化问题 / 基础问题），下可含子分组与问答对集
  // QA_GROUPS 维护用户自建的分组（按 type 分），分组下挂文档 id
  if (!window.QA_GROUPS) window.QA_GROUPS = { gen: [], plain: [] };
  function qaTreeHTML() {
    const dirs = [
      { key: "gen", name: "泛化问题", badge: "泛化问题" },
      { key: "plain", name: "基础问题", badge: "基础问题" }
    ];
    let html = `<div class="tree-h up-title">问答对目录</div>`;
    dirs.forEach(d => {
      const docIds = Object.keys(DOCS).filter(id => (DOCS[id].qa || []).some(q => q.type === d.key));
      const groups = (window.QA_GROUPS[d.key] || []);
      // 目录内容容器（折叠时整体收起）
      let dirBody = "";
      // 子分组
      groups.forEach((g, gi) => {
        const gDocs = g.docIds.filter(id => DOCS[id]);
        dirBody += `<div class="tree-row tree-group" data-dot="qa-group" data-type="${d.key}" data-gi="${gi}">
          <i data-lucide="folder-open" class="tw-ic"></i><span class="tw-name">${g.name}</span><span class="tw-count">${gDocs.length}</span><i data-lucide="chevron-down" class="tw-chev"></i><button class="tree-dots" data-dot="qa-group" data-type="${d.key}" data-gi="${gi}" title="更多操作"><i data-lucide="more-horizontal"></i></button>
        </div>`;
        dirBody += `<div class="tree-children open">${gDocs.map(id => qaChildRowHTML(id, d.key, d.badge)).join("")}</div>`;
      });
      // 未分组的问答对集
      const groupedIds = new Set(groups.flatMap(g => g.docIds));
      const ungrouped = docIds.filter(id => !groupedIds.has(id));
      if (ungrouped.length) {
        dirBody += ungrouped.map(id => qaChildRowHTML(id, d.key, d.badge)).join("");
      }
      html += `<div class="tree-row tree-folder open" data-dot="qa-dir" data-type="${d.key}">
        <i data-lucide="folder" class="tw-ic"></i><span class="tw-name">${d.name}</span><span class="tw-count">${docIds.length}</span><i data-lucide="chevron-down" class="tw-chev"></i><button class="tree-dots" data-dot="qa-dir" data-type="${d.key}" title="更多操作"><i data-lucide="more-horizontal"></i></button>
      </div>`;
      html += `<div class="tree-children open">${dirBody}</div>`;
    });
    return html;
  }
  function qaChildRowHTML(id, typeKey, badge) {
    const doc = DOCS[id];
    const cnt = (doc.qa || []).filter(q => q.type === typeKey).length;
    const active = state.sel.qa === id ? "active" : "";
    return `<div class="tree-row tree-child ${active}" data-dot="qa" data-id="${id}" data-type="${typeKey}" data-qa-id="${id}" data-qa-type="${typeKey}" draggable="true">
      <i data-lucide="file-text" class="tw-ic"></i><span class="tw-name">${doc.name}</span><span class="tw-count">${cnt} 条</span><span class="qa-badge ${typeKey}">${badge}</span><button class="tree-dots" data-dot="qa" data-id="${id}" data-type="${typeKey}" title="更多操作"><i data-lucide="more-horizontal"></i></button>
    </div>`;
  }

  function bindQaTree(container) {
    syncTreeBody(container, qaTreeHTML());
    icons();
    // 目录级（泛化问题 / 基础问题）：展开/折叠 + 拖拽（导入新集 / 接收移动到此目的）
    container.querySelectorAll(".tree-folder").forEach(row => {
      row.addEventListener("click", (e) => {
        if (e.target.closest(".tree-dots")) return;
        row.classList.toggle("open");
        const kids = row.nextElementSibling;
        if (kids && kids.classList.contains("tree-children")) kids.classList.toggle("open");
      });
      row.addEventListener("dragover", (e) => {
        e.preventDefault(); e.stopPropagation();
        const t = e.dataTransfer; const mId = t && t.getData("text/qa-id"); const mType = t && t.getData("text/qa-type");
        if (mId && mType && mType !== row.dataset.type) { e.dataTransfer.dropEffect = "none"; return; }
        row.classList.add("drop-target");
      });
      row.addEventListener("dragleave", () => row.classList.remove("drop-target"));
      row.addEventListener("drop", (e) => {
        e.preventDefault(); e.stopPropagation();
        row.classList.remove("drop-target");
        const files = e.dataTransfer && e.dataTransfer.files;
        const mId = e.dataTransfer && e.dataTransfer.getData("text/qa-id");
        const mType = e.dataTransfer && e.dataTransfer.getData("text/qa-type");
        if (files && files.length) {
          [...files].forEach(f => importQaSet(f, row.dataset.type));
        } else if (mId) {
          if (mType !== row.dataset.type) { toast("仅可移动到相同目的（同为泛化或基础问题）的文件夹"); return; }
          moveQaToGroup(mId, row.dataset.type, -1);
        }
      });
    });
    // 子分组：折叠 + 接收拖入（仅同目的）+ 拖拽移动
    container.querySelectorAll(".tree-group").forEach(row => {
      row.addEventListener("click", (e) => { if (e.target.closest(".tree-dots")) return; row.classList.toggle("open"); const kids = row.nextElementSibling; if (kids && kids.classList.contains("tree-children")) kids.classList.toggle("open"); });
      row.addEventListener("dragover", (e) => {
        e.preventDefault(); e.stopPropagation();
        const t = e.dataTransfer; const mId = t && t.getData("text/qa-id"); const mType = t && t.getData("text/qa-type");
        if (mId && mType && mType !== row.dataset.type) { e.dataTransfer.dropEffect = "none"; return; }
        row.classList.add("drop-target");
      });
      row.addEventListener("dragleave", () => row.classList.remove("drop-target"));
      row.addEventListener("drop", (e) => {
        e.preventDefault(); e.stopPropagation();
        row.classList.remove("drop-target");
        const mId = e.dataTransfer && e.dataTransfer.getData("text/qa-id");
        const mType = e.dataTransfer && e.dataTransfer.getData("text/qa-type");
        if (!mId) return;
        if (mType !== row.dataset.type) { toast("仅可移动到相同目的（同为泛化或基础问题）的文件夹"); return; }
        moveQaToGroup(mId, row.dataset.type, parseInt(row.dataset.gi, 10));
      });
    });
    // 问答对集节点：选中并展示 + 可拖拽到其他同目的文件夹
    container.querySelectorAll(".tree-child").forEach(row => {
      row.addEventListener("click", (e) => {
        if (e.target.closest(".tree-dots")) return;
        container.querySelectorAll(".tree-child.active").forEach(r => r.classList.remove("active"));
        row.classList.add("active");
        state.sel.qa = row.dataset.qa;
        renderLibContent("qa", row.dataset.qa);
      });
      row.addEventListener("dragstart", (e) => {
        e.dataTransfer.setData("text/qa-id", row.dataset.qaId);
        e.dataTransfer.setData("text/qa-type", row.dataset.qaType);
        e.dataTransfer.effectAllowed = "move";
      });
    });
    // 三点菜单：目录 / 分组 / 文档（事件委托，避免图标替换导致 handler 丢失）
    container.addEventListener("click", (e) => {
      const btn = e.target.closest(".tree-dots");
      if (!btn) return;
      e.stopPropagation();
      const row = btn.closest(".tree-row");
      const dot = btn.dataset.dot;
      if (dot === "qa-dir") showQaDirContextMenu(e, btn);
      else if (dot === "qa-group") showQaGroupContextMenu(e, btn);
      else showQaContextMenu(e, btn);
    });
  }

  // 将问答对集移动到目标分组：-1 表示移到该类型目录下的“未分组”区
  function moveQaToGroup(docId, typeKey, gi) {
    const groups = window.QA_GROUPS[typeKey] || [];
    groups.forEach(g => {
      const i = g.docIds.indexOf(docId);
      if (i >= 0) g.docIds.splice(i, 1);
    });
    if (gi >= 0 && groups[gi]) {
      if (!groups[gi].docIds.includes(docId)) groups[gi].docIds.push(docId);
    }
    renderLib("qa");
    state.sel.qa = docId;
    renderLibContent("qa", docId);
    icons();
    toast(gi >= 0 ? `已移动到「${groups[gi].name}」` : `已移到「${typeLabel(typeKey)}」未分组区`);
  }

  // 导入问答对集：创建 DOCS 条目（仅含 qa，无知识点），归类到指定类型
  function importQaSet(file, typeKey) {
    const id = "q" + Date.now().toString(36) + Math.floor(Math.random() * 1000);
    const ext = (file.name.split(".").pop() || "").toUpperCase();
    const type = { PDF: "PDF", DOCX: "DOCX", JSON: "JSON", CSV: "CSV" }[ext] || ext || "FILE";
    const kb = file.size / 1024;
    const size = kb >= 1024 ? (kb / 1024).toFixed(1) + " MB" : Math.max(1, Math.round(kb)) + " KB";
    DOCS[id] = { name: file.name, type, size, status: "已生成", ver: "v1", updated: "刚刚",
      preview: [], versions: [{ tag: "v1", note: `导入问答对集（${typeLabel(typeKey)}）`, time: "刚刚" }],
      kp: [], qa: [], review: [] };
    // 模拟解析为该类型问答对
    const sample = { id: id + "-1", q: file.name.replace(/\.[^.]+$/, "") + " 相关问题？", a: "（已导入，待补充答案）", diff: "中等", review: "待审核", evidence: "—", src: file.name, type: typeKey };
    DOCS[id].qa = [sample];
    renderLib("qa");
    state.sel.qa = id;
    renderLibContent("qa", id);
    toast(`已导入问答对集「${file.name}」至${typeLabel(typeKey)}目录`);
    icons();
  }

  function showQaContextMenu(e, btn) {
    $$(".ctx-popup").forEach(p => p.remove());
    const id = btn.dataset.id;
    const pop = document.createElement("div");
    pop.className = "ctx-popup";
    pop.innerHTML = `<button data-act="qa-export">导出文档</button><button data-act="qa-reupload">重新上传</button>`;
    const rect = btn.getBoundingClientRect();
    pop.style.top = rect.bottom + 4 + "px";
    pop.style.left = Math.min(rect.left, window.innerWidth - 180) + "px";
    document.body.appendChild(pop);
    pop.querySelectorAll("button").forEach(b => {
      b.onclick = () => {
        pop.remove();
        if (b.dataset.act === "qa-export") exportQaSet(id);
        else if (b.dataset.act === "qa-reupload") { const docName = DOCS[id] ? DOCS[id].name : ""; setUploadTarget(findNodeParent(docName) || ""); $("#uploadInput").click(); }
      };
    });
    const closeF = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", closeF); } };
    setTimeout(() => document.addEventListener("click", closeF), 0);
  }

  // 目录级（泛化问题 / 基础问题）右键：新建分组文件夹
  function showQaDirContextMenu(e, btn) {
    $$(".ctx-popup").forEach(p => p.remove());
    const typeKey = btn.dataset.type;
    const pop = document.createElement("div");
    pop.className = "ctx-popup";
    pop.innerHTML = `<button data-act="qa-new-group">新建分组文件夹</button><button data-act="qa-import">拖入/导入问答对集</button>`;
    const rect = btn.getBoundingClientRect();
    pop.style.top = rect.bottom + 4 + "px";
    pop.style.left = Math.min(rect.left, window.innerWidth - 180) + "px";
    document.body.appendChild(pop);
    pop.querySelectorAll("button").forEach(b => {
      b.onclick = () => {
        pop.remove();
        if (b.dataset.act === "qa-new-group") {
          if (!window.QA_GROUPS[typeKey]) window.QA_GROUPS[typeKey] = [];
          window.QA_GROUPS[typeKey].push({ name: "新建分组", docIds: [] });
          renderLib("qa");
        } else if (b.dataset.act === "qa-import") {
          state._qaImportType = typeKey;
          $("#uploadInput").click();
        }
      };
    });
    const closeF = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", closeF); } };
    setTimeout(() => document.addEventListener("click", closeF), 0);
  }

  // 分组级右键：重命名 / 删除分组（删除仅移除分组，不删文档）
  function showQaGroupContextMenu(e, btn) {
    $$(".ctx-popup").forEach(p => p.remove());
    const typeKey = btn.dataset.type;
    const gi = parseInt(btn.dataset.gi, 10);
    const pop = document.createElement("div");
    pop.className = "ctx-popup";
    pop.innerHTML = `<button data-act="qa-group-rename">重命名</button><button data-act="qa-group-delete">删除分组</button>`;
    const rect = btn.getBoundingClientRect();
    pop.style.top = rect.bottom + 4 + "px";
    pop.style.left = Math.min(rect.left, window.innerWidth - 180) + "px";
    document.body.appendChild(pop);
    pop.querySelectorAll("button").forEach(b => {
      b.onclick = () => {
        pop.remove();
        if (b.dataset.act === "qa-group-rename") {
          const g = window.QA_GROUPS[typeKey][gi];
          const nv = prompt("分组名称", g.name);
          if (nv && nv.trim()) { g.name = nv.trim(); renderLib("qa"); }
        } else if (b.dataset.act === "qa-group-delete") {
          window.QA_GROUPS[typeKey].splice(gi, 1);
          renderLib("qa");
          toast("已删除分组（问答对集保留在目录下）");
        }
      };
    });
    const closeF = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", closeF); } };
    setTimeout(() => document.addEventListener("click", closeF), 0);
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
      <div class=" qa-cell qa-q-cell" data-c="q"><span>${q.q}</span></div>
      <div class="qa-cell qa-a-cell" data-c="a"><span>${q.a}</span></div>
      <div class="qa-cell qa-diff-cell" data-c="diff"><span>${q.diff}</span></div>
      <div class="qa-cell qa-review-cell" data-c="review">${reviewBadge(q)}</div>
      <div class="qa-cell qa-ev-cell" data-c="evidence"><span>${q.evidence || "—"}</span></div>
      <div class="qa-cell qa-src-cell" data-c="src"><span>${q.src}</span></div>
      <div class="qa-cell qa-type-cell"><span class="qa-badge ${q.type}">${typeLabel(q.type)}</span></div>
      <span class="ds-actions">
        <button class="btn ghost sm" data-act="qa-edit" title="编辑"><i data-lucide="pencil"></i></button>
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
      <div class="ds-grid">
        <div class="ds-block"><div class="ds-title">难度分布（简单 / 中等 / 难）</div><div class="chart-box"><canvas id="${chartId}"></canvas></div></div>
        <div class="ds-block"><div class="ds-title">质量与人工审核（通过 / 驳回比例）</div>
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
      </div>
      <div class="card card-pad">
        <div class="qa-table" id="qaTable">
          <div class="qa-col-head">
            <div class="qa-cell qa-q-cell">问题<i data-lucide="filter" class="col-filter" data-filter="q"></i></div>
            <div class="qa-cell qa-a-cell">答案<i data-lucide="filter" class="col-filter" data-filter="a"></i></div>
            <div class="qa-cell qa-diff-cell">难度<i data-lucide="filter" class="col-filter" data-filter="diff"></i></div>
            <div class="qa-cell qa-review-cell">审核<i data-lucide="filter" class="col-filter" data-filter="review"></i></div>
            <div class="qa-cell qa-ev-cell">证据<i data-lucide="filter" class="col-filter" data-filter="evidence"></i></div>
            <div class="qa-cell qa-src-cell">来源文档<i data-lucide="filter" class="col-filter" data-filter="src"></i></div>
            <div class="qa-cell qa-type-cell">类型<i data-lucide="filter" class="col-filter" data-filter="type"></i></div>
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
  function addQa(docId, preset) {
    const base = { id: "Q-" + (Date.now() % 100000), q: "新问题（点击单元格编辑）", a: "待补充答案", diff: "简单", review: "待审核", evidence: "—", src: "—" };
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
    // 单元格双击编辑（仿 Excel）
    $$("#qaContent .qa-row .qa-cell[data-c]").forEach(cell => {
      cell.addEventListener("dblclick", () => startCellEdit(cell));
    });
    $$("#qaContent .qa-row").forEach(row => {
      const id = row.dataset.id;
      const edit = row.querySelector("[data-act='qa-edit']"), del = row.querySelector("[data-act='qa-del']");
      if (edit) edit.onclick = () => {
        const d = DOCS[findDocOfQa(id)]; const q = d.qa.find(x => x.id === id);
        const nq = prompt("编辑问题", q.q); if (nq == null) return;
        const na = prompt("编辑答案", q.a); if (na == null) return;
        q.q = nq; q.a = na; showLib("qa");
      };
      if (del) del.onclick = () => {
        const d = DOCS[findDocOfQa(id)];
        if (!confirm("删除该问答对？")) return;
        d.qa = d.qa.filter(x => x.id !== id); showLib("qa");
      };
    });
    const exp = $("#qaExportBtn");
    if (exp) exp.onclick = () => exportQaSet(currentQaDoc());
    $$("#qaContent [data-rv]").forEach(b => {
      b.onclick = () => {
        const d = DOCS[findDocOfQa(b.dataset.id)]; const q = d.qa.find(x => x.id === b.dataset.id);
        if (!q) return; q.review = b.dataset.rv === "pass" ? "已通过" : "已驳回"; showLib("qa");
      };
    });
  }

  // 单元格行内编辑
  function startCellEdit(cell) {
    const row = cell.closest(".qa-row"); const id = row.dataset.id;
    const d = DOCS[findDocOfQa(id)]; const q = d.qa.find(x => x.id === id);
    const field = cell.dataset.c; const span = cell.querySelector("span");
    const cur = field === "review" ? q.review : (q[field] || "");
    const input = document.createElement("input");
    input.className = "cell-edit-input";
    input.value = cur;
    const write = () => {
      let v = input.value.trim();
      if (field === "review") { if (!["已通过", "已驳回", "待审核"].includes(v)) v = "待审核"; }
      if (field === "diff") { if (!["简单", "中等", "难"].includes(v)) v = "简单"; }
      q[field] = v; showLib("qa");
    };
    input.addEventListener("blur", write);
    input.addEventListener("keydown", e => { if (e.key === "Enter") { input.blur(); } else if (e.key === "Escape") { input.value = cur; input.blur(); } });
    cell.innerHTML = ""; cell.appendChild(input); input.focus(); input.select();
  }

  // 列筛选弹层
  const colFilterLabel = { q: "问题", a: "答案", diff: "难度", review: "审核", evidence: "证据", src: "来源文档", type: "类型" };
  function openColFilter(field, anchor) {
    $$(".ctx-popup").forEach(p => p.remove());
    const docId = currentQaDoc(); const d = DOCS[docId]; if (!d) return;
    const vals = [...new Set(d.qa.map(q => field === "review" ? q.review : (q[field] || "—")))].filter(Boolean);
    const pop = document.createElement("div"); pop.className = "ctx-popup col-filter-pop";
    pop.innerHTML = `<div class="up-title">筛选：${colFilterLabel[field] || field}</div>` + vals.map(v => `<label class="cf-item"><input type="checkbox" checked data-v="${v}"/> ${v}</label>`).join("") + `<button class="cf-apply">应用</button>`;
    document.body.appendChild(pop);
    const rect = anchor ? anchor.getBoundingClientRect() : { bottom: 200, left: 200 };
    pop.style.top = (rect.bottom + 6) + "px";
    pop.style.left = Math.min(rect.left, window.innerWidth - 220) + "px";
    const cellClass = { q: "qa-q-cell", a: "qa-a-cell", diff: "qa-diff-cell", review: "qa-review-cell", evidence: "qa-ev-cell", src: "qa-src-cell", type: "qa-type-cell" };
    pop.querySelector(".cf-apply").onclick = () => {
      const keep = new Set([...pop.querySelectorAll("input[data-v]:checked")].map(x => x.dataset.v));
      const cls = cellClass[field] || `qa-${field}-cell`;
      $$("#qaRows .qa-row").forEach(row => {
        const cell = row.querySelector("." + cls);
        const f = field === "review" ? (cell ? cell.textContent.trim() : "—") : ((cell && cell.querySelector("span")) ? cell.querySelector("span").textContent.trim() : "—");
        row.style.display = keep.has(f) ? "" : "none";
      });
      pop.remove();
    };
    const closeF = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", closeF); } };
    setTimeout(() => document.addEventListener("click", closeF), 0);
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
    const payload = {
      doc: d.name,
      qa_count: d.qa.length,
      qa: d.qa.map(q => ({ id: q.id, q: q.q, a: q.a, diff: q.diff, type: typeLabel(q.type), review: q.review, evidence: q.evidence, src: q.src }))
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = d.name.replace(/\.[^.]+$/, "") + "_问答对.json";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast(`已导出「${d.name}」的 ${d.qa.length} 条问答对`);
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
    return `<div class="lib-head"><div class="lh-ic"><i data-lucide="list-checks"></i></div><div><div class="lh-title">${node.name}</div><div class="lh-sub">知识点 · ${all.length} 条</div></div></div>
      <div class="card card-pad">
        <div class="kp-head"><span>编号</span><span>知识点陈述</span><span>类型</span><span>优先级</span><span>状态</span></div>
        ${all.map((k, i) => `<div class="kp-row"><span class="kp-id">KP-${(i + 1).toString().padStart(3, "0")}</span><span class="kp-stmt">${k.stmt}</span><span><span class="pill br">${k.type}</span></span><span class="muted">${k.prio}</span><span><span class="badge ${k.state === "已覆盖" ? "ok" : "warn"}">${k.state}</span></span></div>`).join("")}
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

  /* ---------------- 输入文档库：上传 → 自动抽取知识点 + 下载 ---------------- */
  /* 查找目录节点（在 TREE.children 中按名称递归查找） */
  function findOrCreateFolder(name) {
    const parts = String(name).split("/").map(s => s.trim()).filter(Boolean);
    let parent = TREE, node = null;
    for (const part of parts) {
      node = parent.children.find(n => n.name === part);
      if (!node) { node = { name: part, children: [] }; parent.children.push(node); }
      parent = node;
    }
    return node;
  }

  function createSubFolder(parentName, subName) {
    const parent = findOrCreateFolder(parentName);
    let node = parent.children.find(n => n.name === subName);
    if (!node) { node = { name: subName, children: [] }; parent.children.push(node); }
    return node;
  }

  function readFileText(file) {
    return new Promise(res => {
      const r = new FileReader();
      r.onload = () => res(r.result || "");
      r.onerror = () => res("");
      r.readAsText(file);
    });
  }
  // 从文档文本自动抽取知识点：按句切分 + 类型识别（规则/约束、流程、定义）
  function extractEIU(text) {
    const segs = (text || "").split(/[。；;！!?？\n]+/).map(s => s.trim())
      .filter(s => s.length >= 6 && /[一-龥A-Za-z0-9]/.test(s));
    return segs.slice(0, 40).map((s, i) => {
      const n = (i + 1).toString().padStart(3, "0");
      let type = "定义";
      if (/不得|必须|应当|应|上限|下限|比例|阈值|限制|不超过|超过|禁止/.test(s)) type = "规则/约束";
      else if (/流程|步骤|先|后|提交|审批|办理|操作/.test(s)) type = "流程";
      else if (/是指|称作|即|定义|称为|包括/.test(s)) type = "定义";
      return { id: "KP-U" + n, stmt: s + (s.endsWith("。") ? "" : "。"), type, prio: "必须覆盖", state: "待补充", ev: "上传文档 · 自动抽取" };
    });
  }
  function downloadEIU(docId) {
    const d = DOCS[docId]; if (!d) return;
    const rows = d.kp || [];
    const payload = { doc: d.name, eiu_count: rows.length, eiu: rows };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = d.name.replace(/\.[^.]+$/, "") + "_知识点.json";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast(`已导出「${d.name}」的 ${rows.length} 条知识点（JSON）`);
  }
  function handleUpload(file) {
    const id = "u" + Date.now().toString(36) + Math.floor(Math.random() * 1000);
    const ext = (file.name.split(".").pop() || "").toUpperCase();
    const typeMap = { PDF: "PDF", DOCX: "DOCX", DOC: "DOC", TXT: "TXT", MD: "MD" };
    const type = typeMap[ext] || ext || "FILE";
    const kb = file.size / 1024;
    const size = kb >= 1024 ? (kb / 1024).toFixed(1) + " MB" : Math.max(1, Math.round(kb)) + " KB";
    const targetFolder = state._uploadTarget || "本地上传";
    state._uploadTarget = null;

    DOCS[id] = { name: file.name, type, size, status: "解析中 0%", ver: "v1", updated: "刚刚",
      preview: [], versions: [{ tag: "v1", note: `首次入库（上传至「${targetFolder}」）`, time: "刚刚" }], kp: [], qa: [], review: [], parseProgress: 0 };
    const folder = findOrCreateFolder(targetFolder);
    folder.children.push({ name: file.name, doc: id });

    renderLib("doc");
    state.sel.doc = id;
    renderLibContent("doc", id);
    const tr = $(`#docTree .tree-row[data-doc="${id}"]`);
    if (tr) { $$("#docTree .tree-row.active").forEach(x => x.classList.remove("active")); tr.classList.add("active"); }

    // 模拟进度条
    DOCS[id].parseProgress = 0;
    const progIv = setInterval(() => {
      DOCS[id].parseProgress = Math.min(100, (DOCS[id].parseProgress || 0) + 18 + Math.random() * 12);
      DOCS[id].status = `解析中 ${Math.round(DOCS[id].parseProgress)}%`;
      if (state.view === "doclib" && state.sel.doc === id) renderDocProgress(id);
      if (DOCS[id].parseProgress >= 100) clearInterval(progIv);
    }, 150);

    readFileText(file).then(text => {
      clearInterval(progIv);
      DOCS[id].parseProgress = 100;
      const eius = extractEIU(text);
      DOCS[id].kp = eius;
      DOCS[id].preview = text.split(/\n+/).map(s => s.trim()).filter(Boolean).slice(0, 4);
      DOCS[id].status = eius.length ? `已解析（知识点 ${eius.length} 条）` : "已解析（未识别到可抽取知识点）";
      renderLibContent("doc", id);
      toast(`已上传「${file.name}」并自动抽取 ${eius.length} 条知识点`);
      icons();
    });
  }

  function renderDocProgress(docId) {
    const d = DOCS[docId]; if (!d) return;
    const pg = Math.round(d.parseProgress || 0);
    const bar = document.querySelector(".upload-prog-bar");
    const txt = document.querySelector(".upload-prog-txt");
    if (bar) bar.style.width = pg + "%";
    if (txt) txt.textContent = pg >= 100 ? "解析完成 ✓" : `知识点解析中 ${pg}%`;
  }

  /* ---------------- 问答对生成（选择文件类型 / 配置 / 监控） ---------------- */
  function renderSrcList() {
    renderSrcTree();
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

      let html = `<div class="src-tn" style="padding-left:${depth*18+4}px">`;
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

    $("#srcList").innerHTML = renderNode(TREE, 0);
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

  /* ---------------- 智能问答：对话式操作评测集（分页视图） ---------------- */
  const chatFlow = () => $("#chatFlow");
  function botBubble(html) { const d = document.createElement("div"); d.className = "msg bot"; d.innerHTML = `<div class="bubble">${html}</div>`; chatFlow().appendChild(d); chatFlow().scrollTop = chatFlow().scrollHeight; icons(); }
  function userBubble(t) { const d = document.createElement("div"); d.className = "msg user"; d.innerHTML = `<div class="bubble">${t}</div>`; chatFlow().appendChild(d); chatFlow().scrollTop = chatFlow().scrollHeight; }

  function allQa() { return Object.keys(DOCS).flatMap(id => (DOCS[id].qa || []).map(q => ({ ...q, docId: id, docName: DOCS[id].name }))); }
  function allKp() { return Object.keys(DOCS).flatMap(id => (DOCS[id].kp || []).map(k => ({ ...k, docId: id, docName: DOCS[id].name }))); }

  function confirmCard(opts) {
    const d = document.createElement("div"); d.className = "msg bot";
    d.innerHTML = `<div class="bubble"><div class="confirm-card">
      <div class="cc-t"><i data-lucide="alert-triangle"></i>${opts.title}</div>
      <div class="cc-d">${opts.desc}</div>
      <div class="cc-actions"><button class="btn ghost sm" data-c="cancel">取消</button><button class="btn danger sm" data-c="ok">${opts.confirmText || "确认删除"}</button></div>
    </div></div>`;
    chatFlow().appendChild(d); chatFlow().scrollTop = chatFlow().scrollHeight; icons();
    d.querySelector("[data-c='cancel']").onclick = () => { d.querySelector(".confirm-card").outerHTML = `<div class="cc-done muted"><i data-lucide="info"></i>已取消</div>`; icons(); };
    d.querySelector("[data-c='ok']").onclick = () => { opts.onConfirm(); d.querySelector(".confirm-card").outerHTML = `<div class="cc-done"><i data-lucide="check"></i>${opts.doneText || "操作完成"}</div>`; icons(); };
  }

  function qaListHTML(rows, cap) {
    if (!rows.length) return `<div class="qa-title">${cap || "未找到"}：当前没有匹配的问答对。</div>`;
    return `<div class="qa-title">${cap}</div><div class="qa-list">${rows.map(q => `<div class="qa-item"><div class="qa-head"><span class="qa-id">${q.id}</span><span class="diff ${q.diff}">${q.diff}</span><span class="qa-src">${q.docName}</span></div><div class="qa-q">${q.q}</div><div class="qa-a">${q.a}</div></div>`).join("")}</div>`;
  }

  function chatReply(text) {
    const t = text.trim();
    // —— 删除 ——
    if (t.includes("删除")) {
      const m = t.match(/Q-\d+/i);
      if (m) {
        const id = m[0].toUpperCase();
        const hit = allQa().find(q => q.id === id);
        if (!hit) { botBubble(`未找到编号为 <b>${id}</b> 的问答对。可输入「列出全部问答对」查看现有编号。`); return; }
        confirmCard({ title: "确认删除问答对", desc: `将删除问答对 <b>${id}</b>（${hit.docName}）：${hit.q}`, confirmText: "删除该条", doneText: "已删除 " + id, onConfirm: () => { const d = DOCS[hit.docId]; d.qa = d.qa.filter(x => x.id !== id); state.folderSel.qa = null; renderLibContent("qa", hit.docId); } });
        return;
      }
      const doc = Object.keys(DOCS).find(id => t.includes(DOCS[id].name));
      if (doc) {
        const n = DOCS[doc].qa.length;
        confirmCard({ title: "确认删除问答对集", desc: `将删除「${DOCS[doc].name}」下的全部 ${n} 条问答对，不可撤销。`, confirmText: "删除全部", doneText: "已清空 " + DOCS[doc].name, onConfirm: () => { DOCS[doc].qa = []; state.folderSel.qa = null; renderLibContent("qa", doc); } });
        return;
      }
      botBubble(`请指定要删除的对象：可用编号（如 <b>删除 Q-102</b>）或文档名（如 <b>删除 授信管理办法 问答对</b>）。先输入「列出全部问答对」查看现有编号。`);
      return;
    }
    // —— 查询问答对 ——
    if (t.includes("问答对") || t.includes("获取") || t.includes("导出") || t.includes("列出") || t.includes("列表")) {
      let rows = allQa();
      const diffM = ["简单", "中等", "难"].find(d => t.includes(d)); if (diffM) rows = rows.filter(r => r.diff === diffM);
      const doc = Object.keys(DOCS).find(id => t.includes(DOCS[id].name)); if (doc) rows = rows.filter(r => r.docId === doc);
      const cap = (diffM ? diffM + " 难度 · " : "") + (doc ? DOCS[doc].name + " · " : "") + "共 " + rows.length + " 条问答对";
      botBubble(qaListHTML(rows, cap));
      return;
    }
    // —— 知识点 ——
    if (t.includes("知识点") || t.includes("EIU")) {
      if (t.includes("有哪些") || t.includes("列出") || t.includes("列表") || t.includes("全部")) {
        const all = allKp();
        if (!all.length) { botBubble("当前平台暂无可提取的知识点（相关文档均触发拒答验证、未生成知识点）。"); return; }
        botBubble(`<div class="qa-title">知识点 · 共 ${all.length} 条</div><div class="kp-list">${all.map(k => `<div class="kp-row-card"><div class="kpc-t">${k.stmt}</div><div class="kpc-m">${k.type} · ${k.prio} · ${k.state} · 证据 ${k.ev} · ${k.docName}</div></div>`).join("")}</div>`);
      } else {
        botBubble(`<div class="help-card"><b>知识点</b><br>由业务文档自动提取的可验证知识点，包含 规则 / 流程 / 约束 / 定义 / 指标 等类型，并标注原文证据来源（如「授信政策 §2.3」）。问答对即围绕这些知识点派生。输入「列出知识点」可查看全部。</div>`);
      }
      return;
    }
    // —— 参数输入 ——
    if (t.includes("参数") || t.includes("输入") || t.includes("配置") || t.includes("难度")) {
      botBubble(`<div class="help-card"><b>问答对生成 · 参数输入</b><br>在「问答对生成」选择文件类型后可配置：<ul><li><b>待生成问答文件</b>：跨块问题组合 + 难度多选（简单/中等/难）</li><li><b>待泛化文件</b>：每个原始问题生成 N 个泛化问题，可同时保留原始问题</li></ul></div>`);
      return;
    }
    // —— 平台操作 ——
    if (t.includes("操作") || t.includes("怎么") || t.includes("如何") || t.includes("新建") || t.includes("平台")) {
      botBubble(`<div class="help-card"><b>平台操作指引</b><br><ul><li><b>新建问答对任务</b>：概览页「新建问答对任务」，或在问答对生成选文件→开始生成</li><li><b>上传文档</b>：输入文档库→上传文档，自动解析/分块/抽取知识点</li><li><b>管理问答对</b>：输出问答对库可新增/编辑/删除/审核</li><li><b>导出结果</b>：问答对生成完成后可跳转输出问答对库下载</li></ul>也可以直接对我说「删除 Q-102」「列出 中等 问答对」来操作评测集。</div>`);
      return;
    }
    // —— 泛化 ——
    if (t.includes("泛化")) {
      botBubble(`<div class="help-card"><b>问题泛化</b><br>在已有问答对基础上做同义改写、句式变换与上下文替换，扩充问题多样性以提升评测鲁棒性。在「问答对生成」选择「待泛化文件」后，设置每个原始问题生成的泛化数量，直接点击「开始生成」即可。</div>`);
      return;
    }
    // —— 默认 ——
    botBubble(`我可以对话式操作平台评测集：<ul><li>删除某条：<b>删除 Q-102</b></li><li>清空某文档：<b>删除 授信管理办法 问答对</b></li><li>查询：<b>列出全部问答对</b> / <b>列出 中等 问答对</b></li><li>知识点：<b>列出知识点</b></li><li>参数 / 操作：<b>参数怎么填</b> / <b>怎么新建任务</b></li></ul>`);
  }

  function setupChat() {
    $("#chatSend").onclick = sendChat;
    $("#chatInput").addEventListener("keydown", e => { if (e.key === "Enter") sendChat(); });
    $$(".ask-chip").forEach(c => c.onclick = () => { const q = c.dataset.q; userBubble(q); chatReply(q); });
    if (!chatFlow().childElementCount) {
      botBubble(`你好，我是问答对生成平台助手。可以通过对话直接操作平台评测集：<ul><li>删除某条问答对：<b>删除 Q-102</b></li><li>查询问答对：<b>列出 中等 问答对</b></li><li>列出知识点 / 了解参数与平台操作</li></ul>左侧或下方输入即可开始。`);
    }
  }
  function sendChat() { const v = $("#chatInput").value; if (!v.trim()) return; userBubble(v); $("#chatInput").value = ""; setTimeout(() => chatReply(v), 200); }

  /* ---------------- 事件绑定 / 初始化 ---------------- */
  function bindGlobal() {
    $("#nav").addEventListener("click", e => { const it = e.target.closest(".nav-item"); if (it) goto(it.dataset.view); });
    // 智能问答：固定浮层对话，贴右下角
    const content = $("#content"), divider = $("#splitDivider"), right = $("#splitRight");
    const trees = [$("#docTree"), $("#qaTree")];
    // 「重新展开」按钮吸在浏览器视口左边缘：挂在 body 上，避免被 .view 的 transform 包含块捕获
    let rb = document.querySelector(".tree-reopen");
    if (!rb) {
      rb = document.createElement("button");
      rb.className = "tree-reopen";
      rb.textContent = "展开目录";
      document.body.appendChild(rb);
    }
    rb.onclick = () => { trees.forEach(t => { if (!t) return; t.classList.remove("collapsed"); const split = t.closest(".lib-split"); if (split) split.classList.remove("tree-hidden"); }); applyTreeHidden(); };
    function applyTreeHidden() {
      let anyHidden = false;
      trees.forEach(t => {
        if (!t) return;
        const split = t.closest(".lib-split");
        if (split) split.classList.toggle("tree-hidden", t.classList.contains("collapsed"));
        if (t.classList.contains("collapsed")) anyHidden = true;
      });
      // 任一目录收起时，在页面最左边吸附显示「展开目录」按钮
      rb.classList.toggle("show", anyHidden);
    }
    function toggleAsk(force) {
      const on = (typeof force === "boolean") ? force : !content.classList.contains("split-on");
      content.classList.toggle("split-on", on);
      divider.hidden = !on; right.hidden = !on; right.classList.remove("ask-max"); content.classList.remove("ask-full");
      $("#askBtn").classList.toggle("active", on);
      // 点击智能问答后，仅输入文档库与输出问答对库这两个栏目的目录缩放（收起），让内容占满
      trees.forEach(t => { if (t) t.classList.toggle("collapsed", on); });
      applyTreeHidden();
    }
    $("#askBtn").onclick = () => toggleAsk();
    $("#askClose").onclick = () => toggleAsk(false);
    // 目录树隐藏/显示按钮（输入库与输出库各一个），点击直接隐藏，并同步重新展开按钮
    ["treeToggle", "treeToggle2"].forEach(id => {
      const btn = document.getElementById(id);
      if (btn) {
        const tree = btn.closest(".tree");
        if (tree) btn.onclick = () => { tree.classList.add("collapsed"); applyTreeHidden(); };
      }
    });
    applyTreeHidden();
    // 智能问答窗口：全屏放大 / 缩小固定（无拖拽改大小）
    const askMax = $("#askMax");
    if (askMax) askMax.onclick = () => {
      const max = right.classList.toggle("ask-max");
      content.classList.toggle("ask-full", max);
      askMax.innerHTML = `<i data-lucide="${max ? "minimize-2" : "maximize-2"}"></i>`;
      icons();
    };
    // 概览：面板 / 列表展开
    document.addEventListener("click", e => {
      const ph = e.target.closest(".panel-head"); if (ph) { const p = ph.closest(".panel"); p.classList.toggle("open"); return; }
      const lr = e.target.closest(".list-row.expandable"); if (lr) { lr.classList.toggle("open"); return; }
      const go = e.target.closest("[data-go]"); if (go) { goto(go.dataset.go); return; }
      const dl = e.target.closest(".mr-dl-link[data-goto]"); if (dl) { e.preventDefault(); goto(dl.dataset.goto); return; }
    });
    // 问答对生成：来源类型切换 → 选项随类型变化
    $("#srcTypeSeg").addEventListener("click", e => {
      const b = e.target.closest("button[data-type]"); if (!b) return;
      $$("#srcTypeSeg button").forEach(x => x.classList.toggle("on", x === b));
      state.studioType = b.dataset.type;
      state.srcCollapsed = {};
      renderSrcList();
      renderStudioOpts();
    });
    // 运行并监控
    $("#studioRun").onclick = () => {
      const typeLabel = { doc: "待生成问答文件", qa: "待泛化文件" }[state.studioType];
      const srcIds = state.studioSrc || [];
      if (!srcIds.length) { toast("请先选择文件"); return; }
      // 检查是否有可生成的内容
      let hasContent = false;
      if (state.studioType === "doc") {
        hasContent = srcIds.some(id => DOCS[id] && DOCS[id].kp && DOCS[id].kp.length > 0);
      } else {
        hasContent = srcIds.some(id => DOCS[id] && DOCS[id].qa && DOCS[id].qa.length > 0);
      }
      if (!hasContent) { toast("无问题"); return; }
      // 待泛化文件：检查难度是否勾选
      if (state.studioType === "doc" && state.studioOpts.difficulties.length === 0) { toast("请至少选择一种难度"); return; }
      let name;
      if (srcIds.length === 1) {
        name = (DOCS[srcIds[0]] || {}).name || srcIds[0];
      } else {
        name = srcIds.length + " 个文档";
      }
      const row = document.createElement("div"); row.className = "monitor-row";
      const tag = state.studioType === "doc" ? `难度${state.studioOpts.difficulties.join("/")}${state.studioOpts.flatOutput ? "·扁平" : "·层级"}` : `×${state.studioOpts.generalizeCount}`;
      row.innerHTML = `<span class="mr-name">${name} · ${typeLabel} · ${tag}</span><span class="mr-bar"><span style="width:0%"></span></span><span class="mr-pct">0%</span>`;
      $("#monitorList").prepend(row);
      let p = 0; const bar = row.querySelector(".mr-bar > span"), pct = row.querySelector(".mr-pct");
      const iv = setInterval(() => { p += 14; if (p >= 100) { p = 100; clearInterval(iv); pct.innerHTML = '<a href="#" class="mr-dl-link" data-goto="qalib">下载</a>'; pct.querySelector(".mr-dl-link").onclick = e => { e.preventDefault(); goto("qalib"); }; } bar.style.width = p + "%"; if (p < 100) pct.textContent = p + "%"; }, 180);
      const label = state.studioType === "doc" ? "问答对生成" : "问题泛化";
      toast(`已启动：${name} · ${label}`);
    };
    $("#bellBtn").onclick = () => toast("提醒：知识抽取完成 · 评测完成 · 待人工审核 12 条");
    // 输入文档库：上传文档 → 选择目标目录 → 自动抽取知识点（含进度展示）
    const uploadInput = $("#uploadInput");
    if (uploadInput) {
      $("#uploadBtn").onclick = () => {
        $$(".ctx-popup").forEach(p => p.remove());
        const pop = document.createElement("div");
        pop.className = "ctx-popup upload-picker";
        pop.innerHTML = `<div class="up-title">选择上传目标目录</div>` +
          flattenFolders().map(f => `<button data-folder="${f}">${f}</button>`).join("") +
          `<button data-folder="">根目录（不分类）</button>`;
        const btnEl = $("#uploadBtn");
        const rect = btnEl.getBoundingClientRect();
        pop.style.top = rect.bottom + 6 + "px";
        pop.style.left = Math.min(rect.left, window.innerWidth - 200) + "px";
        document.body.appendChild(pop);
        pop.querySelectorAll("button").forEach(b => {
          b.onclick = () => { pop.remove(); setUploadTarget(b.dataset.folder || undefined); uploadInput.click(); };
        });
        const closeUp = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", closeUp); } };
        setTimeout(() => document.addEventListener("click", closeUp), 0);
      };
      uploadInput.addEventListener("change", e => {
        if (state._qaImportType) {
          const t = state._qaImportType; state._qaImportType = null;
          [...e.target.files].forEach(f => importQaSet(f, t));
        } else {
          [...e.target.files].forEach(f => handleUpload(f));
        }
        uploadInput.value = "";
      });
    }
    setupChat();
  }

  function toast(msg) {
    const t = $("#toast"); t.textContent = msg; t.style.display = "block";
    clearTimeout(toast._t); toast._t = setTimeout(() => t.style.display = "none", 2200);
  }

  // 启动
  renderNav(); syncBell(); bindGlobal(); renderSrcList(); renderStudioOpts(); goto("overview");
})();

