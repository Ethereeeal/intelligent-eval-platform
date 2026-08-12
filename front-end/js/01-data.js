  const $ = (s, r = document) => r.querySelector(s);
  const $$ = (s, r = document) => [...r.querySelectorAll(s)];

  /* 浮层定位：按锚点元素在视口内摆放弹层，超出边界时自动翻转/收敛，避免显示到浏览器窗口之外。
     pop 需已挂载到 DOM 且为 position:fixed；anchor 为触发按钮。 */
  function placePopup(pop, anchor, gap = 4, edge = 8) {
    if (!pop || !anchor) return;
    const rect = anchor.getBoundingClientRect();
    const pw = pop.offsetWidth, ph = pop.offsetHeight;
    // 垂直：默认锚点下方，放不下则翻到上方，仍放不下则贴视口边缘
    let top = rect.bottom + gap;
    if (top + ph > window.innerHeight - edge) {
      const above = rect.top - ph - gap;
      top = above >= edge ? above : Math.max(edge, window.innerHeight - ph - edge);
    }
    if (top < edge) top = edge;
    // 水平：默认与锚点左对齐，超出右边界则右对齐，再收敛进视口
    let left = rect.left;
    if (left + pw > window.innerWidth - edge) left = rect.right - pw;
    if (left + pw > window.innerWidth - edge) left = window.innerWidth - pw - edge;
    if (left < edge) left = edge;
    pop.style.top = top + "px";
    pop.style.left = left + "px";
    pop.style.visibility = "";
  }

  /* 锚点是否真实可见：既要在视口内，也不能被内部滚动容器（如目录树 .tree）裁剪掉。
     仅判断视口是不够的——目录树自身 overflow:auto，滚出去的行仍会返回视口内坐标。 */
  function isAnchorVisible(anchor) {
    if (!anchor || !document.body.contains(anchor)) return false;
    const r = anchor.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) return false;
    // 视口边界
    if (r.bottom <= 0 || r.top >= window.innerHeight || r.right <= 0 || r.left >= window.innerWidth) return false;
    // 逐级检查带裁剪的祖先容器
    let n = anchor.parentElement;
    while (n && n !== document.body) {
      const s = getComputedStyle(n);
      if (["auto", "scroll", "hidden"].includes(s.overflowY) || ["auto", "scroll", "hidden"].includes(s.overflowX)) {
        const cr = n.getBoundingClientRect();
        // 锚点中心点落在容器可视区之外则视为不可见
        const cy = r.top + r.height / 2, cx = r.left + r.width / 2;
        if (cy < cr.top || cy > cr.bottom || cx < cr.left || cx > cr.right) return false;
      }
      n = n.parentElement;
    }
    return true;
  }

  /* 浮层生命周期：滚动时跟随锚点重定位；锚点滚出可视区（含被内部容器裁剪）或被移除则自动关闭。
     返回 cleanup 函数；外部点击关闭逻辑一并接管。 */
  function bindPopupLifecycle(pop, anchor, gap, edge) {
    // 三点按钮默认 hover 才显示；菜单打开期间强制保持可见，否则鼠标移开后锚点尺寸归零
    const hostRow = anchor.closest && anchor.closest(".tree-row");
    if (hostRow) hostRow.classList.add("menu-open");
    const cleanup = () => {
      if (hostRow) hostRow.classList.remove("menu-open");
      pop.remove();
      document.removeEventListener("click", onDocClick, true);
      window.removeEventListener("scroll", onScroll, true);
      window.removeEventListener("resize", onResize);
    };
    const onScroll = () => {
      if (!isAnchorVisible(anchor)) { cleanup(); return; }
      placePopup(pop, anchor, gap, edge);
    };
    const onResize = () => placePopup(pop, anchor, gap, edge);
    const onDocClick = (ev) => { if (!pop.contains(ev.target)) cleanup(); };
    // 先挂一次，等浏览器把本次点击冒泡完再监听，避免立刻被自己的 click 关掉
    setTimeout(() => {
      if (!document.body.contains(pop)) return;
      window.addEventListener("scroll", onScroll, true);
      window.addEventListener("resize", onResize);
      document.addEventListener("click", onDocClick, true);
    }, 0);
    return cleanup;
  }
  // 图标渲染：lucide 若未就绪则静默跳过，避免直接抛错阻断后续逻辑
  const icons = () => { if (window.lucide) { try { lucide.createIcons(); } catch (e) {} } bindKpColFilters(); };

  /* ---------------- 数据模型 ----------------
     说明：原前端以「写死的 mock 数据」驱动全部功能。
     现在改为：优先从后端真实 API 拉取并映射成原有 DOCS/TREE 结构；
     后端 demo 未实现的字段（文档全文预览 preview、版本记录 versions、人工复核 review、泛化问题 gen 来源）
     一律留空（空数组/空串），由原有 UI 的空态逻辑自然呈现，不编造数据。 */

  // 后端基础地址：studio nginx 已对 /api/ 做反向代理到 backend，前后端同源（均走 8080），无需跨域
  const API_BASE = "";
  // 当前用户：无真实登录体系，统一为 web（与上传 upload_user 一致）；
  // 文件夹按 owner 记录归属，为后续真实账号隔离预留
  const CURRENT_USER = "web";
  // 文档库统一模型：所有输入文档归入单一根目录「文档库」，用户可自由新建文件夹/子目录组织；
  // 不再区分「基础问题输入文档 / 仅泛化输入文档」两类系统目录。

  // DOCS 由 loadData() 填充；这里先声明为可变对象，保证其余逻辑可直接读写
  let DOCS = {};
  // TREE：输入文档库目录树，单一根「文档库」，其下为用户自建文件夹与文档
  let TREE = { name: "文档库", children: [] };
  // 各文档归属的输入用途（统一为 basic=基础问题输入；是否泛化由生成界面选择）
  let DOC_PURPOSE = {};
  // 后端持久化的文件夹扁平列表（[{folder_id, name, parent_id}]），
  // 输出问答对库目录树据此重建，保证空文件夹与层级刷新后不丢失。
  let QA_FOLDERS = [];
  // 文档用途判定：所有输入文档统一视为基础问题输入（basic），仅泛化/问答对生成在生成界面选择
  function docPurposeOf(d) {
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
      const [folders, docs, eiuResp, cases] = await Promise.all([
        apiGet(`/api/folders`).catch(() => []),
        apiGet(`/api/documents`),
        apiGet(`/api/eiu`).catch(() => ({ total: 0, items: [] })),
        apiGet(`/api/cases`).catch(() => [])
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
      // 先按后端持久化的文件夹重建目录树（含空文件夹，刷新后不丢失）
      TREE.children = buildFolderTree(folders || []);
      // 输出问答对库复用同一份持久化文件夹（与输入文档库同构）；
      // 各自独立构造节点对象，避免两棵树共享节点导致折叠态互相串扰。
      QA_FOLDERS = folders || [];
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
          type: qaType,
          // 后端持久化的问答对目录归属（相对「问答对库」根），用于输出问答对库目录树
          caseId: c.case_id,
          folderPath: c.folder_path || "",
          purpose: c.purpose || purpose
        }));
        // 问答对集在「问答对库」中的目录归属：取其问答对上后端持久化的 folder_path；
        // 后端尚未回填时（历史数据）兜底沿用源文档的 folder_path，保持与输入库同构。
        const qaFolderPath = (qa.find(x => x.folderPath) || {}).folderPath || (d.folder_path || "");
        DOCS[id] = {
          name: d.file_name, type: (d.file_type || "").replace(/^\./, "").toUpperCase(),
          size: fmtSize(d.file_size), status: statusCN(d.parse_status),
          ver: "", updated: (d.created_at || "").slice(0, 10), purpose, qaFolderPath,
          preview: [],        // 文档原文改为「在线查看」时按需从后端 blocks 接口拉取
          versions: [],       // demo 后端未提供版本记录 → 留空
          kp, qa, review: []  // review：demo 未单独建模 → 留空
        };
        DOC_PURPOSE[id] = purpose;
        // 按后端 folder_path 重建目录树（保留上传时的目录层级），缺省挂到「文档库」根
        insertDocIntoFolderTree(d.folder_path || "", id, d.file_name);
      });
      // 演示数据补齐：已解析（跑通）但后端未返回问答对的文档，生成一份确定性示例问答对，
      // 以便「输出问答对库」能展示问答对表与难度占比（真实后端返回时以真实数据为准，不覆盖）。
      // 注：2026-08 已移除该兜底——真实后端联调后，仅展示数据库真实问答对；
      // 删除文档问答对后若再补示例数据会误导用户（表现为「删了还有假数据」）。
      // 如需纯前端演示再启用 sampleQaForDoc 兜底。
    } catch (err) {
      console.error("加载后端数据失败，所有文档区将显示为空：", err);
      toast("后端数据加载失败，请确认服务已启动（http://localhost:8000）");
      DOCS = {};
      TREE.children = [];
      DOC_PURPOSE = {};
      QA_FOLDERS = [];
    }
  }

  // 将文档按 folder_path 插入到「文档库」子树中，保留层级结构。
  // folder_path 形如「子A/子B」（相对文档库根），或为空表示直接挂在文档库根下。
  function insertDocIntoFolderTree(folderPath, docId, docName) {
    const parts = String(folderPath || "").split("/").map(s => s.trim()).filter(Boolean);
    let parent = TREE;
    for (const part of parts) {
      let node = parent.children.find(n => n.name === part && !n.doc);
      if (!node) { node = { name: part, children: [] }; parent.children.push(node); }
      parent = node;
    }
    parent.children.push({ name: docName, doc: docId });
  }

  // 后端 folder 扁平列表（[{folder_id, name, parent_id}]）→ 嵌套目录树（仅文件夹）。
  // parent_id 为 null 的节点挂在「文档库」根下；空文件夹也会生成节点，保证刷新后保留。
  function buildFolderTree(folderList) {
    const byParent = {};
    (folderList || []).forEach(f => {
      const key = (f.parent_id == null) ? "root" : f.parent_id;
      (byParent[key] = byParent[key] || []).push(f);
    });
    function make(parentKey) {
      return (byParent[parentKey] || []).map(f => {
        const node = { name: f.name, children: [], folderId: f.folder_id };
        node.children = make(f.folder_id);
        return node;
      });
    }
    return make("root");
  }

  // 文件夹节点相对「文档库」根的子路径（如「子A/子B」），空串 = 根
  function relPathOfNode(node) {
    return fullFolderPathOf(node).split("/").filter(p => p && p !== TREE.name).join("/");
  }

  // 由文件夹节点递归得到其完整路径（用 / 连接），根为「文档库」。
  function fullFolderPathOf(node) {
    if (node === TREE) return TREE.name;
    const path = [];
    function walk(children, trail) {
      for (const n of children) {
        if (n === node) { path.push(...trail, n.name); return true; }
        if (n.children && walk(n.children, [...trail, n.name])) return true;
      }
      return false;
    }
    walk(TREE.children, [TREE.name]);
    return path.join("/");
  }

  // 将 TREE 节点对象绑定到上传选择器 DOM 的 .up-node，便于点击时取完整路径
  function bindTreeNodes(domRoot, nodes) {
    const wraps = domRoot.querySelectorAll(":scope > .up-node-wrap");
    nodes.forEach((node, i) => {
      const wrap = wraps[i];
      if (!wrap) return;
      const row = wrap.querySelector(":scope > .up-node");
      if (row) row.__node = node;
      if (node.children && node.children.length) bindTreeNodes(wrap.querySelector(":scope > .up-children"), node.children);
    });
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

