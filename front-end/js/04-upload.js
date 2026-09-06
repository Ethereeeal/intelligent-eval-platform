  /* ---------------- 输入文档库：上传 → 自动抽取知识点 + 下载 ---------------- */
  window.__uploadJobs = window.__uploadJobs || {};

  function renderUploadJobs() {
    const jobs = Object.values(window.__uploadJobs || {}).filter(job => !job.dismissed);
    let box = $("#docUploadProgress");
    if (!jobs.length) {
      if (box) box.remove();
      return;
    }
    if (!box) {
      box = document.createElement("section");
      box.id = "docUploadProgress";
      box.className = "doc-upload-progress-popover";
      document.body.appendChild(box);
    }
    const completed = jobs.filter(job => job.done).length;
    box.innerHTML = `<div class="doc-upload-progress-head"><strong>文档上传与解析</strong><b>${completed}/${jobs.length} 完成</b></div><div class="doc-upload-progress-list">${jobs.map(job => {
      const progress = Math.max(0, Math.min(100, Math.round(job.progress || 0)));
      return `<div class="doc-upload-progress-row"><div class="doc-upload-progress-name"><span>${escapeHTML(job.fileName)}</span><b>${job.done ? (job.failed ? "失败" : "完成") : progress > 30 ? `${progress}%` : "准备中"}</b></div><div class="doc-upload-progress-track"><span class="${job.failed ? "failed" : ""}" style="width:${progress}%"></span></div><div class="doc-upload-progress-status">${escapeHTML(job.status || "处理中…")}</div></div>`;
    }).join("")}</div>`;
  }

  function updateUploadJob(id, patch) {
    const job = window.__uploadJobs[id];
    if (!job) return;
    Object.assign(job, patch);
    if (job.doc) {
      if (patch.status != null) job.doc.status = patch.status;
      if (patch.progress != null) job.doc.parseProgress = patch.progress;
    }
    renderUploadJobs();
  }

  function dismissUploadJob(id, delay = 5000) {
    const job = window.__uploadJobs[id];
    if (!job) return;
    clearTimeout(job.dismissTimer);
    job.dismissTimer = setTimeout(() => {
      if (window.__uploadJobs[id] === job) {
        job.dismissed = true;
        delete window.__uploadJobs[id];
        renderUploadJobs();
      }
    }, delay);
  }

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
  async function handleUpload(file, folderPath) {
    const id = "u" + Date.now().toString(36) + Math.floor(Math.random() * 1000);
    const ext = (file.name.split(".").pop() || "").toLowerCase();
    const typeMap = { pdf: "PDF", docx: "DOCX", doc: "DOC", txt: "TXT", md: "MD", xlsx: "XLSX", csv: "CSV" };
    const type = typeMap[ext] || ext.toUpperCase() || "FILE";
    const kb = file.size / 1024;
    const size = kb >= 1024 ? (kb / 1024).toFixed(1) + " MB" : Math.max(1, Math.round(kb)) + " KB";
    // folderPath：完整目标目录路径（含根「文档库」，如「文档库/子A/子B」）；缺省挂到文档库根
    const targetFull = folderPath || "";
    // 相对文档库根的子路径（如「子A/子B」），空串表示文档库根
    const relPath = targetFull.split("/").filter(p => p && p !== TREE.name).join("/");
    const purpose = "basic"; // 统一基础问题输入，是否泛化由生成界面决定
    state._uploadPurpose = null;
    state._uploadFolderPath = null;

    DOCS[id] = { name: file.name, type, size, status: "上传中…", ver: "v1", updated: "刚刚",
      preview: [], versions: [{ tag: "v1", note: `首次入库（上传至「${targetFull || TREE.name}」）`, time: "刚刚" }], kp: [], qa: [], review: [], parseProgress: 0, folderPath: relPath, qaFolderPath: relPath };
    window.__uploadJobs[id] = { localId: id, docId: null, fileName: file.name, relPath, doc: DOCS[id], progress: 0, status: "上传中…", done: false, failed: false };
    renderUploadJobs();
    insertDocIntoFolderTree(relPath, id, file.name);

    renderLib("doc");
    state.sel.doc = id;
    renderLibContent("doc", id);
    const tr = $(`#docTree .tree-row[data-doc="${id}"]`);
    if (tr) { $$("#docTree .tree-row.active").forEach(x => x.classList.remove("active")); tr.classList.add("active"); }

    try {
      // 1) 上传到后端（folder_path 为相对文档库根的子路径，保留目录结构层级）
      const fd = new FormData();
      fd.append("purpose", purpose);
      if (relPath) fd.append("folder_path", relPath);
      fd.append("file", file);
      fd.append("upload_user", "web");
      fd.append("document_version", "v1");
      DOCS[id].status = "上传中…";
      updateUploadJob(id, { status: "上传中…", progress: 10 });
      renderLibContent("doc", id);
      const up = await fetch(API_BASE + "/api/documents/upload", { method: "POST", body: fd });
      if (!up.ok) throw new Error("上传失败：" + up.status);
      const upRes = await up.json();
      const docId = upRes.document_id;
      updateUploadJob(id, { docId, status: "已入库，解析中…", progress: 30 });
      renderLibContent("doc", id);

      // 2) 触发 EIU 知识点抽取（仅当前文档，单文档隔离，不重抽其他文档）
      const ex = await fetch(API_BASE + `/api/eiu/extract?document_id=${docId}`, { method: "POST" });
      let jobId = null;
      if (ex.ok) { const exRes = await ex.json(); jobId = exRes.job_id; }

      // 3) 轮询抽取进度
      if (jobId != null) {
        const poll = setInterval(async () => {
          try {
            if (!window.__uploadJobs[id]) { clearInterval(poll); return; }
            const jr = await fetch(API_BASE + `/api/jobs/${jobId}`);
            if (!jr.ok) return;
            const job = await jr.json();
            const pg = Math.max(0, Math.min(100, Number(job.progress) || 0));
            // 上传完成占 0–30%，EIU 抽取按后端每 10 个 Block 的离散进度映射到 30–99%。
            const overallProgress = Math.max(30, Math.min(99, 30 + Math.round(pg * 0.69)));
            updateUploadJob(id, { progress: overallProgress, status: "知识点抽取中" });
            if ((state.view === "doclib" || (state.view === "evalset" && window.__esView === "doclib")) && state.sel.doc === id) renderDocProgress(id);
            if (job.finished || job.status === "completed" || job.status === "failed") {
              clearInterval(poll);
              const wasSelected = state.sel.doc === id;
              const failed = job.status === "failed";
              updateUploadJob(id, { progress: failed ? pg : 100, status: failed ? "解析失败" : "解析完成", done: true, failed });
              await loadData();                    // 重新拉取后端最新文档/知识点（覆盖临时文档）
              const realId = "doc" + docId;
              if (wasSelected) state.sel.doc = realId;
              renderLib("doc");
              if (wasSelected) {
                const tr2 = $(`#docTree .tree-row[data-doc="${realId}"]`);
                if (tr2) { $$("#docTree .tree-row.active").forEach(x => x.classList.remove("active")); tr2.classList.add("active"); }
              }
              if (failed) {
                toast(`「${file.name}」入库成功，但知识点抽取失败`);
                dismissUploadJob(id, 7000);
                icons();
                return;
              }
              // 4) 入库 + 知识点抽取完成：不自动生成评测集。
              //    EIU 已持久化在文档库，之后用户可在评测集库中选择该文档生成评测集。
              dismissUploadJob(id, 2500);
              toast(`「${file.name}」上传成功，可前往评测集库进行生成`);
              icons();
            }
          } catch (e) { /* 忽略单次轮询错误 */ }
        }, 1500);
      } else {
        const wasSelected = state.sel.doc === id;
        updateUploadJob(id, { progress: 100, status: "解析完成", done: true });
        await loadData();
        const realId = "doc" + docId;
        if (wasSelected) state.sel.doc = realId;
        renderLib("doc");
        dismissUploadJob(id, 2500);
        toast(`「${file.name}」上传成功，可前往评测集库进行生成`);
        icons();
      }
    } catch (e) {
      const message = "上传失败：" + (e.message || e);
      updateUploadJob(id, { status: message, progress: 0, done: true, failed: true, retain: true });
      if (DOCS[id]) renderLibContent("doc", id);
      dismissUploadJob(id, 7000);
      toast("上传失败：" + (e.message || e));
      icons();
    }
  }

  function renderDocProgress(docId) {
    const d = DOCS[docId]; if (!d) return;
    const pg = Math.round(d.parseProgress || 0);
    const bar = document.querySelector("#docContent .upload-prog-bar");
    const txt = document.querySelector("#docContent .upload-prog-txt");
    if (bar) bar.style.width = pg + "%";
    if (txt) txt.textContent = pg >= 100 ? "解析完成 ✓" : `解析进度 ${pg}%`;
  }

  // 入口：entries = [{ file, folderPath }]；文档允许重复，全部直接上传
  async function handleUploadSelection(entries) {
    entries.forEach(e => handleUpload(e.file, e.folderPath));
  }
