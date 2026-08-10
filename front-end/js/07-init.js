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
    // 输入文档库：上传文档 → 选择目标目录（点击弹出 overlay 目录树）→ 自动抽取知识点
    const uploadInput = $("#uploadInput");
    const folderInput = $("#uploadFolderInput");
    if (uploadInput) {
      // 点击上传按钮：弹出 overlay modal，内部为目录树选择器，可滚动/折叠
      $("#uploadBtn").onclick = () => {
        $$(".ctx-popup").forEach(p => p.remove());
        const mask = document.createElement("div");
        mask.className = "up-modal-mask";
        mask.innerHTML = `<div class="up-modal">` +
          `<div class="up-modal-head"><span>选择上传目标目录</span>` +
          `<button class="up-close" title="关闭">×</button></div>` +
          `<div class="up-modal-body"><div class="up-tree">${uploadTreeHTML(TREE.children)}</div></div>` +
          `<div class="up-modal-foot">` +
          `<button class="up-pick-file">上传文件</button>` +
          `<button class="up-pick-folder">上传文件夹（保留目录结构）</button>` +
          `</div>` +
          `<div class="up-hint">文档须归属「基础问题输入文档 / 仅泛化输入文档」系统目录之一（可在其内部任意子目录间组织）。</div>` +
          `</div>`;
        document.body.appendChild(mask);
        if (window.lucide) window.lucide.createIcons();
        const closeModal = () => mask.remove();
        mask.querySelector(".up-close").onclick = closeModal;
        mask.addEventListener("click", (e) => { if (e.target === mask) closeModal(); });
        // 目录树：点击文件夹节点（系统目录或内部任意子目录）即选中为目标；文档节点忽略；非系统文件夹可展开/折叠
        mask.querySelectorAll(".up-node").forEach(row => {
          row.addEventListener("click", (e) => {
            e.stopPropagation();
            if (row.dataset.doc) return; // 文档不可作为上传目标
            if (row.dataset.folder && !row.dataset.system) {
              row.parentElement.classList.toggle("collapsed");
            }
            mask.querySelectorAll(".up-node").forEach(r => r.classList.remove("sel"));
            row.classList.add("sel");
            state._uploadFolderPath = fullFolderPathOf(row.__node);
          });
        });
        // 绑定树节点对象到 DOM，便于取完整路径
        bindTreeNodes(mask.querySelector(".up-tree"), TREE.children);
        // 选文件上传
        mask.querySelector(".up-pick-file").onclick = () => {
          if (!state._uploadFolderPath) { toast("请先选择目标目录", "warn"); return; }
          closeModal();
          uploadInput.click();
        };
        // 选文件夹上传（保留目录结构）
        if (folderInput) {
          mask.querySelector(".up-pick-folder").onclick = () => {
            if (!state._uploadFolderPath) { toast("请先选择目标目录", "warn"); return; }
            closeModal();
            folderInput.click();
          };
        } else {
          mask.querySelector(".up-pick-folder").style.display = "none";
        }
      };
      // 单文件上传：按已选 folder_path 上传
      uploadInput.addEventListener("change", e => {
        if (state._qaImportType) {
          const t = state._qaImportType; state._qaImportType = null;
          [...e.target.files].forEach(f => importQaSet(f, t));
        } else if (state._uploadFolderPath) {
          [...e.target.files].forEach(f => handleUpload(f, state._uploadFolderPath));
        }
        uploadInput.value = "";
      });
      // 文件夹上传：保留相对目录结构，每个文件 folder_path = 目标/相对路径
      if (folderInput) {
        folderInput.addEventListener("change", e => {
          if (!state._uploadFolderPath) { toast("请先选择目标目录", "warn"); return; }
          const base = state._uploadFolderPath;
          [...e.target.files].forEach(f => {
            let rel = (f.webkitRelativePath || f.relativePath || "").split("/").slice(0, -1).join("/");
            const fp = rel ? `${base}/${rel}` : base;
            handleUpload(f, fp);
          });
          folderInput.value = "";
        });
      }
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
