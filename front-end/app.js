/* ============================================================
   问答对生成平台 — 交互逻辑
   栏目：概览 / 问答对生成 / 输入文档库 / 输出问答对库
   ============================================================ */
(function () {
  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];
  // 图标渲染：lucide 若未就绪则静默跳过，避免直接抛错阻断后续逻辑
  const icons = () => { if (window.lucide) { try { lucide.createIcons(); } catch (e) {} } bindKpColFilters(); };

  /* ---------------- 数据模型 ----------------
     说明：原前端以「写死的 mock 数据」驱动全部功能。
     现在改为：优先从后端真实 API 拉取并映射成原有 DOCS/TREE 结构；
     后端 demo 未实现的字段（文档全文预览 preview、版本记录 versions、人工复核 review、泛化问题 gen 来源）
     一律留空（空数组/空串），由原有 UI 的空态逻辑自然呈现，不编造数据。 */

  // 后端基础地址（demo 后端运行在 8000 端口；如需跨机访问可改为对应 IP）
  const API_BASE = (location.port === "8000") ? "" : "http://localhost:8000";
  // 默认载入的语料库（corpus）。demo 主数据为 corpus_id=2；可在控制台 window.__CORPUS_ID 覆盖
  // activeCorpusId 为可变当前语料库：每次上传会新建独立 corpus 并切换过去，保证不同上传隔离、不混
  let activeCorpusId = window.__CORPUS_ID || 2;
  const CORPUS_ID = activeCorpusId;

  // DOCS 由 loadData() 填充；这里先声明为可变对象，保证其余逻辑可直接读写
  let DOCS = {};
  // TREE：输入文档库目录树，保持原始「全部文档 → 基础问题输入文档 / 泛化问题输入文档」两棵子树结构
  let TREE = { name: "全部文档", children: [
    { name: "基础问题输入文档", purpose: "basic", desc: "需经知识点抽取生成基础问答对", children: [] },
    { name: "仅泛化输入文档", purpose: "gen", desc: "本身即问答对，无需抽取知识点，直接作为泛化问答对输入", children: [] }
  ] };
  // 各文档归属的输入用途（basic=基础问题输入文档 gen=泛化问题输入文档）
  let DOC_PURPOSE = {};
  // 文档用途判定：真实后端不返回「文档用途」字段，按业务规则推断——
  // 当前 demo 仅做了「基础问答对生成」（m03 产出基础问答对），故真实文档均归 basic；
  // 若后续接入「本身即问答对」的泛化输入文档，将其 purpose 置为 "gen" 即可。
  function docPurposeOf(d) {
    // 预留：可在此依据 d.tags / 文件名 / 业务标记切换为 "gen"
    return "basic";
  }

  function fmtSize(bytes) {    if (bytes == null) return "—";
    if (bytes < 1024) return bytes + " B";
    if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(1) + " KB";
    return (bytes / 1024 / 1024).toFixed(1) + " MB";
  }
  function statusCN(s) {
    if (!s) return "未解析";
    if (s === "completed") return "已解析";
    if (s === "failed") return "解析失败";
    if (s === "parsing") return "解析中";
    if (s === "pending") return "待解析";
    return s;
  }
  function diffCN(d) {
    return { L1: "简单", L2: "中等", L3: "难", L4: "难" }[d] || (d || "—");
  }
  function reviewCN(r) {
    if (r === "quality_verified" || r === "approved") return "已通过";
    if (r === "rejected") return "已驳回";
    if (r === "blocked") return "已阻断";
    return "待审核";
  }
  function evText(ev) {
    // cases.evidence：数组对象，取「提取知识点的原文」(block_text/content/text)，不含来源路径
    // eiu.evidence_blocks：数组 id，原样拼接
    if (Array.isArray(ev)) {
      const parts = ev.map(e => {
        if (e && typeof e === "object") {
          const o = (e.evidence && typeof e.evidence === "object") ? e.evidence : e;
          return o.block_text || o.content || o.text || "";
        }
        return typeof e === "string" ? e : "";
      }).filter(Boolean);
      return parts.join("；") || "—";
    }
    return ev ? String(ev) : "—";
  }
  function evBack(ev) {
    // 证据后段：从 evidence 块提取「原文句子」(block_text/content/sentence/text)，区别于前段定位路径
    if (Array.isArray(ev)) {
      const parts = ev.map(e => {
        if (e && typeof e === "object") {
          const o = (e.evidence && typeof e.evidence === "object") ? e.evidence : e;
          return o.block_text || o.content || o.sentence || o.text || "";
        }
        return typeof e === "string" ? e : "";
      }).filter(Boolean);
      return parts.join("；") || "";
    }
    return "";
  }
  function evSrc(ev) {
    // 提取知识点的来源文档/章节路径
    if (Array.isArray(ev)) {
      for (const e of ev) {
        const o = (e && typeof e === "object") ? ((e.evidence && typeof e.evidence === "object") ? e.evidence : e) : null;
        if (o && (o.section_path || o.source || o.doc)) return o.section_path || o.source || o.doc;
      }
      return "—";
    }
    return "—";
  }
  function evSec(ev) {
    // 知识点证据列统一用「章节」展示：优先取 evidence 块的 section_path
    if (Array.isArray(ev)) {
      const secs = ev.map(e => {
        const o = (e && typeof e === "object") ? ((e.evidence && typeof e === "object") ? e.evidence : e) : null;
        return o && o.section_path ? o.section_path : "";
      }).filter(Boolean);
      return secs.join("；") || "（无章节）";
    }
    return "（无章节）";
  }
  // 知识点章节：后端 eiu 顶层直接带 section_path（由关联 Block 注入），evidence_blocks 只是 block id 列表，不能取章节。
  // 故优先取 e.section_path；兼容旧结构（evidence_blocks 内嵌对象）作为回退。
  function kpSec(e) {
    if (e && e.section_path) return e.section_path;
    if (e && Array.isArray(e.evidence_blocks)) {
      const secs = e.evidence_blocks.map(x => {
        const o = (x && typeof x === "object") ? ((x.evidence && typeof x.evidence === "object") ? x.evidence : x) : null;
        return o && o.section_path ? o.section_path : "";
      }).filter(Boolean);
      if (secs.length) return secs.join("；");
    }
    return "（无章节）";
  }
  function escapeHTML(s) {
    return String(s).replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }
  // 演示数据：为「已解析但无问答对」的文档生成确定性示例问答对（含难度分布），便于展示问答对表与难度占比
  function sampleQaForDoc(d, docId, qaType) {
    const kpStmts = (d.kp || []).map(k => k.stmt).filter(Boolean);
    const baseQ = d.name.replace(/\.[^.]+$/, "");
    const diffs = ["简单", "中等", "难"];
    const n = 9; // 9 条，保证三种难度均有分布
    const rows = [];
    for (let i = 0; i < n; i++) {
      const diff = diffs[i % 3];
      const kp = kpStmts.length ? kpStmts[i % kpStmts.length] : `${baseQ}相关要点`;
      rows.push({
        id: "Q-" + docId + "-" + (i + 1),
        q: `关于「${baseQ}」的${diff === "简单" ? "基础" : diff === "中等" ? "常见" : "深入"}问题 ${i + 1}：请说明其与哪些规则/流程相关？`,
        a: `${baseQ}的${diff === "简单" ? "基本概念" : diff === "中等" ? "主要处理逻辑" : "边界与例外情况"}。依据：${kp}`,
        diff,
        review: i % 4 === 3 ? "待审核" : "已通过",
        evidence: kp,
        src: "示例问答对（演示数据）",
        type: qaType
      });
    }
    return rows;
  }

  async function apiGet(path) {
    const res = await fetch(API_BASE + path, { headers: { "Accept": "application/json" } });
    if (!res.ok) throw new Error(path + " -> " + res.status);
    return res.json();
  }

  // 从后端拉取并映射成原有 DOCS/TREE/DOC_PURPOSE 结构
  async function loadData() {
    try {
      const [docs, eiuResp, cases] = await Promise.all([
        apiGet(`/api/documents?corpus_id=${activeCorpusId}`),
        apiGet(`/api/corpus/${activeCorpusId}/eiu`).catch(() => ({ total: 0, items: [] })),
        apiGet(`/api/corpus/${activeCorpusId}/cases`).catch(() => [])
      ]);
      const eius = (eiuResp && eiuResp.items) || [];
      const eiuByDoc = {};
      eius.forEach(e => {
        if (e.is_questionable === false) return; // 排除项不计入知识点
        (eiuByDoc[e.document_id] = eiuByDoc[e.document_id] || []).push(e);
      });
      const caseByDoc = {};
      (cases || []).forEach(c => {
        (caseByDoc[c.document_id] = caseByDoc[c.document_id] || []).push(c);
      });

      DOCS = {};
      TREE.children.forEach(c => c.children = []);
      DOC_PURPOSE = {};

      (docs || []).forEach(d => {
        const id = "doc" + d.document_id;
        const purpose = docPurposeOf(d); // basic 或 gen
        const kp = (eiuByDoc[d.document_id] || []).map((e, i) => ({
          id: "KP-" + e.eiu_id,
          stmt: e.statement || "",
          type: ({ rule: "规则", constraint: "约束", definition: "定义", process: "流程" }[e.eiu_type] || "规则"),
          prio: ({ P1: "必须覆盖", P2: "建议覆盖", P3: "可选覆盖" }[e.content_priority] || "建议覆盖"),
          // 后端未提供证据/来源时，兜底填充这两个字段，保证前端非空展示
          // 证据列统一用「章节」(section_path)；来源文档直接用文件名
          chapter: kpSec(e),
          source_doc: d.file_name || "（无）",
          ev: kpSec(e),
          src: d.file_name || "（无）"
        }));
        // qa.type 由文档用途决定：基础问题输入文档产出「基础问题」(plain)，泛化输入文档产出「泛化问题」(gen)
        const qaType = purpose === "gen" ? "gen" : "plain";
        const qa = (caseByDoc[d.document_id] || []).map(c => ({
          id: "Q-" + c.case_id,
          q: c.question || "",
          a: c.gold_answer || c.answer || "",
          diff: diffCN(c.difficulty),
          review: reviewCN(c.review_status),
          // 后端未提供证据/来源文档时，兜底填充这两个字段，保证前端非空展示
          // 证据列统一用「章节」(section_path)；来源文档直接用文件名
          src: d.file_name || "（无）",
          evidence: evSec(c.evidence) || (c.gold_answer || c.answer || c.question || "（无）"),
          // 证据后段：后端若仅提供证据前段（定位/来源路径）而未给后段原文，则补充该字段并输出。
          // 优先取 evidence 块内的原文句子（block_text/content/text），后端无则兜底为空串，由展示层标「（无）」。
          evidence2: evBack(c.evidence) || (c.gold_answer || c.answer || c.question || ""),
          type: qaType
        }));
        DOCS[id] = {
          name: d.file_name, type: (d.file_type || "").replace(/^\./, "").toUpperCase(),
          size: fmtSize(d.file_size), status: statusCN(d.parse_status),
          ver: "", updated: (d.created_at || "").slice(0, 10), purpose,
          preview: [],        // 文档原文改为「在线查看」时按需从后端 blocks 接口拉取
          versions: [],       // demo 后端未提供版本记录 → 留空
          kp, qa, review: []  // review：demo 未单独建模 → 留空
        };
        DOC_PURPOSE[id] = purpose;
        const folder = TREE.children.find(c => c.purpose === purpose);
        if (folder) folder.children.push({ name: d.file_name, doc: id });
      });
      // 演示数据补齐：已解析（跑通）但后端未返回问答对的文档，生成一份确定性示例问答对，
      // 以便「输出问答对库」能展示问答对表与难度占比（真实后端返回时以真实数据为准，不覆盖）。
      Object.keys(DOCS).forEach(id => {
        const d = DOCS[id];
        const parsed = /已解析/.test(d.status);
        if (parsed && (!d.qa || d.qa.length === 0)) {
          const qaType = d.purpose === "gen" ? "gen" : "plain";
          d.qa = sampleQaForDoc(d, id, qaType);
        }
      });
    } catch (err) {
      console.error("加载后端数据失败，所有文档区将显示为空：", err);
      toast("后端数据加载失败，请确认服务已启动（http://localhost:8000）");
      DOCS = {};
      TREE.children.forEach(c => c.children = []);
      DOC_PURPOSE = {};
    }
  }

  const state = {
    view: "overview",
    sel: { doc: "d1", kp: "d1", qa: "d1" },
    folderSel: { doc: null, kp: null, qa: null },
    studioType: "doc",
    studioSrc: ["d1"],
    studioGenOn: false,   // 是否进行泛化流程（全局开关，生成结果是否为泛化问题）
    studioOpts: { crossBlock: true, crossDoc: true, difficulties: ["简单","中等","难"], generalizeCount: 3, keepOriginal: true, flatOutput: false }
  };

  const charts = {};

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
    const isGen = DOC_PURPOSE[docId] === "gen";
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
        ${isGen ? `<div class="gen-input-note"><i data-lucide="info"></i><div>本输入文档属于「仅泛化输入文档」，<b>本身即问答对，无需抽取知识点</b>，将直接作为泛化问答对输入使用。</div></div>` : `<div class="sec-h mt kp-sec-h">知识点 · ${d.kp.length} 条<button class="btn ghost sm kp-export-btn" id="dlEIUKp"><i data-lucide="download"></i>导出</button><button class="btn ghost icon-only sm kp-zoom-btn" id="kpFullscreenBtn" title="放大查看"><i data-lucide="maximize"></i></button></div>
        ${d.kp && d.kp.length ? kpTableHTML(d.kp) : `<p class="muted mt">${isParsing ? "正在解析中..." : "未识别到可抽取知识点。"}</p>`}`}
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
        state.sel.qa = row.dataset.id;
        renderLibContent("qa", row.dataset.id);
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
        if (keep.has(f)) { row.style.display = ""; delete row.dataset.filtered; }
        else { row.style.display = "none"; row.dataset.filtered = "1"; }
      });
      state.qaPage = 1; refreshPagers(); pop.remove();
    };
    const closeF = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", closeF); } };
    setTimeout(() => document.addEventListener("click", closeF), 0);
  }

  // 知识点表格列筛选（与问答对列筛选机制一致）
  const kpColFilterLabel = { stmt: "知识点", prio: "推荐", type: "类型", ev: "证据", src: "来源文档" };
  function openKpColFilter(field, anchor) {
    $$(".ctx-popup").forEach(p => p.remove());
    const pop = document.createElement("div"); pop.className = "ctx-popup col-filter-pop";
    const cells = $$(`.kp-c-${field}`);
    const vals = [...new Set(cells.map(c => c.textContent.replace(/^#\d+\s*/, "").trim()).filter(Boolean))];
    pop.innerHTML = `<div class="up-title">筛选：${kpColFilterLabel[field] || field}</div>` + vals.map(v => `<label class="cf-item"><input type="checkbox" checked data-v="${escapeHTML(v)}"/> ${escapeHTML(v)}</label>`).join("") + `<button class="cf-apply">应用</button>`;
    document.body.appendChild(pop);
    const rect = anchor ? anchor.getBoundingClientRect() : { bottom: 200, left: 200 };
    pop.style.top = (rect.bottom + 6) + "px";
    pop.style.left = Math.min(rect.left, window.innerWidth - 220) + "px";
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
    const closeF = (ev) => { if (!pop.contains(ev.target)) { pop.remove(); document.removeEventListener("click", closeF); } };
    setTimeout(() => document.addEventListener("click", closeF), 0);
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
  function exportQaRows(rows, name) {
    if (!rows || !rows.length) { toast("当前没有可导出的问答对"); return; }
    const payload = {
      doc: name,
      qa_count: rows.length,
      qa: rows.map(q => ({ id: q.id, q: q.q, a: q.a, diff: q.diff, type: typeLabel(q.type), review: q.review, evidence: q.evidence, src: q.src }))
    };
    const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = (name || "问答对集").replace(/[\\/:*?"<>|]/g, "_") + "_问答对.json";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast(`已导出「${name}」的 ${rows.length} 条问答对`);
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

  function downloadEIU(docId) {
    const d = DOCS[docId]; if (!d) return;
    const rows = d.kp || [];
    // 导出 CSV：知识点 / 推荐 / 类型 / 证据(章节) / 来源文档，Excel 友好（含 BOM）
    const head = ["知识点", "推荐", "类型", "证据", "来源文档"];
    const esc = (v) => `"${String(v == null ? "" : v).replace(/"/g, '""')}"`;
    const lines = [head.map(esc).join(",")];
    rows.forEach(k => lines.push([k.stmt, k.prio, k.type, k.ev, k.src].map(esc).join(",")));
    const csv = "﻿" + lines.join("\r\n");
    const blob = new Blob([csv], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = d.name.replace(/\.[^.]+$/, "") + "_知识点.csv";
    document.body.appendChild(a); a.click(); a.remove();
    URL.revokeObjectURL(url);
    toast(`已导出「${d.name}」的 ${rows.length} 条知识点（CSV）`);
  }

  // 上传文档到后端真实链路：上传 → 入库/解析分块 → 触发 EIU 知识点抽取 → 轮询进度 → 刷新文档库
  async function handleUpload(file) {
    const id = "u" + Date.now().toString(36) + Math.floor(Math.random() * 1000);
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const typeMap = { pdf: "PDF", docx: "DOCX", doc: "DOC", txt: "TXT", md: "MD" };
    const type = typeMap[ext] || ext.toUpperCase() || "FILE";
    const kb = file.size / 1024;
    const size = kb >= 1024 ? (kb / 1024).toFixed(1) + " MB" : Math.max(1, Math.round(kb)) + " KB";
    const targetFolder = state._uploadTarget || "本地上传";
    state._uploadTarget = null;

    DOCS[id] = { name: file.name, type, size, status: "上传中…", ver: "v1", updated: "刚刚",
      preview: [], versions: [{ tag: "v1", note: `首次入库（上传至「${targetFolder}」）`, time: "刚刚" }], kp: [], qa: [], review: [], parseProgress: 0 };
    const folder = findOrCreateFolder(targetFolder);
    folder.children.push({ name: file.name, doc: id });

    renderLib("doc");
    state.sel.doc = id;
    renderLibContent("doc", id);
    const tr = $(`#docTree .tree-row[data-doc="${id}"]`);
    if (tr) { $$("#docTree .tree-row.active").forEach(x => x.classList.remove("active")); tr.classList.add("active"); }

    try {
      // 0) 每次上传都新建一个独立语料库（corpus），保证不同上传之间完全隔离、不混在一起
      const ts = new Date();
      const pad = (n) => String(n).padStart(2, "0");
      const tsStr = `${ts.getFullYear()}${pad(ts.getMonth() + 1)}${pad(ts.getDate())}_${pad(ts.getHours())}${pad(ts.getMinutes())}${pad(ts.getSeconds())}`;
      const corpusName = `上传_${tsStr}_${file.name}`;
      let corpusId = CORPUS_ID;
      try {
        const cRes = await fetch(API_BASE + "/api/corpus", {
          method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ name: corpusName, description: `单次上传自动创建（${file.name}）`, created_by: "web" })
        });
        if (cRes.ok) { const cJson = await cRes.json(); corpusId = cJson.corpus_id; }
        activeCorpusId = corpusId;
      } catch (e) { /* 建库失败则回退到默认 corpus */ }

      // 1) 上传到后端（使用本次新建的 corpus_id）
      const fd = new FormData();
      fd.append("corpus_id", String(corpusId));
      fd.append("file", file);
      fd.append("upload_user", "web");
      fd.append("document_version", "v1");
      DOCS[id].status = "上传中…";
      renderLibContent("doc", id);
      const up = await fetch(API_BASE + "/api/documents/upload", { method: "POST", body: fd });
      if (!up.ok) throw new Error("上传失败：" + up.status);
      const upRes = await up.json();
      // 完全禁止重复上传：内容已存在则拦截，不上传、不抽取、提示已存在
      if (upRes.duplicate) {
        delete DOCS[id];
        renderLib("doc");
        toast(`「${file.name}」已存在，未重复上传`);
        icons();
        return;
      }
      const docId = upRes.document_id;
      DOCS[id].status = "已入库，解析中…";
      DOCS[id].parseProgress = 30;
      renderLibContent("doc", id);

      // 2) 触发 EIU 知识点抽取（仅当前文档，单文档隔离，不重抽其他文档）
      const ex = await fetch(API_BASE + `/api/corpus/${corpusId}/eiu/extract?document_id=${docId}`, { method: "POST" });
      let jobId = null;
      if (ex.ok) { const exRes = await ex.json(); jobId = exRes.job_id; }

      // 3) 轮询抽取进度
      if (jobId != null) {
        const poll = setInterval(async () => {
          try {
            const jr = await fetch(API_BASE + `/api/jobs/${jobId}`);
            if (!jr.ok) return;
            const job = await jr.json();
            const pg = job.progress || 0;
            DOCS[id].parseProgress = Math.max(30, Math.min(99, pg));
            DOCS[id].status = `知识点抽取中 ${Math.round(pg)}%`;
            if (state.view === "doclib" && state.sel.doc === id) renderDocProgress(id);
            if (job.finished || job.status === "completed" || job.status === "failed") {
              clearInterval(poll);
              await loadData();                    // 重新拉取后端最新文档/知识点（覆盖临时文档）
              const realId = "doc" + docId;
              state.sel.doc = realId;
              renderLib("doc");
              renderLibContent("doc", realId);
              const tr2 = $(`#docTree .tree-row[data-doc="${realId}"]`);
              if (tr2) { $$("#docTree .tree-row.active").forEach(x => x.classList.remove("active")); tr2.classList.add("active"); }
              if (job.status === "failed") {
                toast(`「${file.name}」入库成功，但知识点抽取失败`);
                icons();
                return;
              }
              // 4) 单文档问答对生成：仅当前文档，不混库、不重抽其他文档
              toast(`「${file.name}」知识点已抽取，正在生成问答对…`);
              try {
                const gq = await fetch(
                  API_BASE + `/api/corpus/${corpusId}/cases/generate?document_id=${docId}`,
                  { method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ angles: ["primary"], include_variations: false, dry_run: false }) }
                );
                if (gq.ok) {
                  const gqr = await gq.json().catch(() => null);
                  await loadData();
                  if (gqr && typeof gqr.reused === "number" && gqr.reused > 0) {
                    toast(`「${file.name}」复用旧库问答对 ${gqr.reused} 道、新生成 ${gqr.generated || 0} 道`);
                  } else {
                    toast(`「${file.name}」已自动解析知识点并生成问答对`);
                  }
                }
              } catch (e) { /* 问答对生成失败不影响知识点结果 */ }
              await loadData();
              state.sel.doc = realId;
              renderLib("doc");
              renderLibContent("doc", realId);
              icons();
            }
          } catch (e) { /* 忽略单次轮询错误 */ }
        }, 1500);
      } else {
        await loadData();
        const realId = "doc" + docId;
        state.sel.doc = realId;
        renderLib("doc");
        renderLibContent("doc", realId);
        toast(`「${file.name}」已上传入库（未触发知识点抽取）`);
        icons();
      }
    } catch (e) {
      DOCS[id].status = "上传失败：" + (e.message || e);
      DOCS[id].parseProgress = 0;
      renderLibContent("doc", id);
      toast("上传失败：" + (e.message || e));
      icons();
    }
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
      const srcIds = state.studioSrc || [];
      if (!srcIds.length) { toast("请先选择文件"); return; }
      // 待生成问答文件：需勾选至少一种难度
      if (state.studioType === "doc" && state.studioOpts.difficulties.length === 0) { toast("请至少选择一种难度"); return; }
      // 演示环境：后端生成服务未实现，不跑假进度；直接展示已选文件并提供「导出已有问答对」
      renderMonitor();
      const totalQa = srcIds.reduce((s, id) => s + ((DOCS[id] && DOCS[id].qa) ? DOCS[id].qa.length : 0), 0);
      const label = state.studioType === "doc" ? "问答对生成" : "问题泛化";
      toast(`演示环境：生成服务未接入；已列出 ${srcIds.length} 个已选文件，可导出其现有问答对（共 ${totalQa} 条）`);
    };

    $("#bellBtn").onclick = () => {
      const pending = NAV.filter(n => n.badge && n.badge.unread)
        .reduce((s, n) => s + unreadCount(n.view), 0);
      toast(pending
        ? `提醒：知识抽取完成 · 评测完成 · 新生成问答对 ${pending} 个尚未查看`
        : "提醒：知识抽取完成 · 评测完成 · 暂无待查看的新问答对");
    };
    // 输出问答对库：页面级「导出问答对」（导出当前选中文档/目录下全部问答对）
    const qaLibExport = $("#qaLibExportBtn");
    if (qaLibExport) qaLibExport.onclick = () => {
      const rows = currentQaRows();
      const name = state.folderSel.qa ? state.folderSel.qa : (state.sel.qa && DOCS[state.sel.qa] ? DOCS[state.sel.qa].name : "全部问答对");
      exportQaRows(rows, name);
    };
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

  // 启动：先拉取后端真实数据，再渲染（未实现部分自然留空）
  (async function boot() {
    await loadData();
    // 默认选中第一份文档（若有）
    const firstDoc = Object.keys(DOCS)[0];
    if (firstDoc) { state.sel.doc = firstDoc; state.sel.kp = firstDoc; state.sel.qa = firstDoc; state.studioSrc = [firstDoc]; }
    renderNav(); syncBell(); bindGlobal(); renderSrcList(); renderStudioOpts(); renderMonitor(); goto("overview");
    fillOverviewStats();
  })();

  // 概览：问答对总量 + 一句文档大致内容概览（不展示建议/多跳/回溯率等）
  function fillOverviewStats() {
    const docCount = Object.keys(DOCS).length;
    const qaTotal = Object.values(DOCS).reduce((s, d) => s + (d.qa ? d.qa.length : 0), 0);
    const el = $("#kpiQaTotal");
    if (el) el.textContent = qaTotal;

    const ins = $("#hlInsight");
    if (!ins) return;
    if (!docCount) { ins.textContent = "当前暂无已加载的输入文档。"; return; }
    const topics = new Set();
    Object.values(DOCS).forEach(d => {
      (d.purposes && d.purposes.length ? d.purposes : ["基础问题输入文档"]).forEach(p => {
        topics.add(p === "gen" ? "泛化问题" : "基础问题");
      });
    });
    const topicTxt = [...topics].join("、");
    ins.textContent = `当前输入文档库共 ${docCount} 篇文档（含 ${topicTxt}），已生成 ${qaTotal} 条问答对，内容围绕银行证券业务规则与合规要点。`;
  }
})();

