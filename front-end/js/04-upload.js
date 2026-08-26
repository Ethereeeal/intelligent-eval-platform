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
      // 完全禁止重复上传：内容已存在则拦截，不上传、不抽取、提示已存在
      if (upRes.duplicate) {
        delete window.__uploadJobs[id];
        delete DOCS[id];
        renderLib("doc");
        renderUploadJobs();
        toast(`「${file.name}」已存在，未重复上传`);
        icons();
        return;
      }
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

  /* ---------------- 混合上传：预检 → 异常确认 → 上传 ---------------- */
  function escHtml(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, c => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;"
    }[c]));
  }

  function fmtSizeShort(n) {
    if (n == null) return "";
    const kb = n / 1024;
    return kb >= 1024 ? (kb / 1024).toFixed(1) + " MB" : Math.max(1, Math.round(kb)) + " KB";
  }

  function fmtTime(s) {
    if (!s) return "时间未知";
    const d = new Date(s);
    if (isNaN(d.getTime())) return s;
    const p = n => String(n).padStart(2, "0");
    return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`;
  }

  async function precheckFile(file, relPath) {
    const fd = new FormData();
    if (relPath) fd.append("folder_path", relPath);
    fd.append("file", file);
    const res = await fetch(API_BASE + "/api/documents/precheck", { method: "POST", body: fd });
    if (!res.ok) {
      let msg = "预检失败：" + res.status;
      try { const j = await res.json(); if (j.detail) msg = j.detail; } catch (e) { /* ignore */ }
      throw new Error(msg);
    }
    return res.json();
  }

  // 入口：entries = [{ file, folderPath }]；正常文件直接上传，异常文件进确认面板
  async function handleUploadSelection(entries) {
    const direct = [];
    const anomaly = [];
    const skipped = [];
    const CONCURRENCY = 3; // 限并发预检，避免大文件夹同时打满后端（每个预检都会读全文件）
    let cursor = 0;
    async function worker() {
      while (cursor < entries.length) {
        const entry = entries[cursor++];
        const relPath = String(entry.folderPath || "").split("/").filter(p => p && p !== TREE.name).join("/");
        let res;
        try {
          res = await precheckFile(entry.file, relPath);
        } catch (e) {
          toast("预检失败，按正常上传处理：" + (e.message || ""), "warn");
          direct.push(entry);
          continue;
        }
        if (res.status === "duplicate") {
          skipped.push(entry.file.name);
        } else if (res.status === "conflict" || (res.status === "ok" && res.same_name_elsewhere && res.same_name_elsewhere.length)) {
          anomaly.push({ entry, res });
        } else {
          direct.push(entry);
        }
      }
    }
    await Promise.all(Array.from({ length: Math.min(CONCURRENCY, entries.length) }, () => worker()));
    if (skipped.length) {
      toast("已存在，未重复上传：" + [...new Set(skipped)].join("、"), "warn");
    }
    direct.forEach(e => handleUpload(e.file, e.folderPath));
    if (anomaly.length) showUploadConfirmPanel(anomaly);
  }

  function showUploadConfirmPanel(anomaly) {
    $$(".up-confirm-mask").forEach(m => m.remove());
    const removed = new Set();
    const rows = anomaly.map((item, idx) => {
      const res = item.res;
      const conflict = res.status === "conflict";
      const detail = conflict
        ? `将覆盖「${res.existing_folder || "文档库"}/${res.existing_name}」（上次上传 ${fmtTime(res.existing_upload_time)}，${fmtSizeShort(res.existing_size)}）`
        : `其他位置已有同名：` + res.same_name_elsewhere
            .map(d => `「${(d.folder_path || "文档库")}/${d.file_name}」`).join("、") + `；本次将新建，不覆盖`;
      return `<div class="up-confirm-row" data-idx="${idx}">
        <div class="up-confirm-info">
          <div class="up-confirm-name">${escHtml(item.entry.file.name)} <span class="up-confirm-tag ${conflict ? "c" : "w"}">${conflict ? "将覆盖" : "弱提示"}</span></div>
          <div class="up-confirm-detail">${escHtml(detail)}</div>
        </div>
        <button class="up-confirm-remove" data-idx="${idx}" type="button">移除</button>
      </div>`;
    }).join("");

    const mask = document.createElement("div");
    mask.className = "up-modal-mask up-confirm-mask";
    mask.innerHTML = `<div class="up-modal">
      <div class="up-modal-head"><span>上传确认（${anomaly.length} 个文件需确认）</span><button class="up-close" type="button" title="关闭">×</button></div>
      <div class="up-modal-body"><div class="up-confirm-list">${rows}</div></div>
      <div class="up-modal-foot">
        <button class="up-confirm-cancel" type="button">取消全部</button>
        <button class="up-confirm-ok" type="button">确认上传</button>
      </div>
      <div class="up-hint">确认后将覆盖同名文件并重新解析、重抽知识点、重建评测集；「移除」的文件不会上传。</div>
    </div>`;
    document.body.appendChild(mask);
    const close = () => mask.remove();
    mask.querySelector(".up-close").onclick = close;
    mask.addEventListener("click", e => { if (e.target === mask) close(); });
    mask.querySelector(".up-confirm-cancel").onclick = close;
    mask.querySelector(".up-confirm-ok").onclick = () => {
      const okBtn = mask.querySelector(".up-confirm-ok");
      if (okBtn) { okBtn.disabled = true; okBtn.textContent = "处理中…"; }
      close();
      anomaly.forEach((item, idx) => {
        if (removed.has(idx)) return;
        if (item.res.status === "conflict") {
          handleReuploadWithConfirm(item.entry.file, item.res.existing_document_id, item.res.confirm_token);
        } else {
          handleUpload(item.entry.file, item.entry.folderPath);
        }
      });
    };
    mask.querySelectorAll(".up-confirm-remove").forEach(btn => {
      btn.onclick = () => {
        const idx = Number(btn.dataset.idx);
        removed.add(idx);
        const row = btn.closest(".up-confirm-row");
        if (row) row.remove();
        const left = anomaly.filter((_, i) => !removed.has(i)).length;
        const okBtn = mask.querySelector(".up-confirm-ok");
        if (okBtn) okBtn.textContent = left ? `确认上传（剩余 ${left} 个）` : "确认上传（无）";
        if (okBtn) okBtn.disabled = !left;
      };
    });
  }

  async function handleReuploadWithConfirm(file, docId, token) {
    const fd = new FormData();
    fd.append("file", file);
    fd.append("confirm_token", token);
    const up = await fetch(API_BASE + `/api/documents/${docId}/reupload`, { method: "POST", body: fd });
    if (!up.ok) {
      let msg = "覆盖更新失败：" + up.status;
      try { const j = await up.json(); if (j.detail) msg = j.detail; } catch (e) { /* ignore */ }
      toast(msg, "warn");
      return;
    }
    const res = await up.json();
    toast("已开始覆盖更新：重解析 → EIU 重抽 → 版本重建");
    pollReuploadJob(res.job_id, file.name);
  }

  function pollReuploadJob(jobId, fileName) {
    const progressId = `reupload-${jobId}`;
    window.__uploadJobs[progressId] = { localId: progressId, docId: null, fileName: fileName || "覆盖更新文档", progress: 0, status: "覆盖更新中…", done: false, failed: false };
    renderUploadJobs();
    const finish = (msg, failed) => {
      updateUploadJob(progressId, { progress: failed ? 0 : 100, status: msg, done: true, failed: !!failed });
      dismissUploadJob(progressId, failed ? 7000 : 2500);
    };
    const poll = setInterval(async () => {
      try {
        const jr = await fetch(API_BASE + `/api/jobs/${jobId}`);
        if (!jr.ok) return;
        const job = await jr.json();
        if (job.progress != null) updateUploadJob(progressId, { progress: job.progress, status: `覆盖更新中 ${job.progress}%（${job.phase || ""}）` });
        if (job.finished || job.status === "completed" || job.status === "done" || job.status === "failed") {
          clearInterval(poll);
          await loadData();
          if (job.status === "failed") {
            finish("覆盖更新失败：" + (job.message || ""), true);
            toast("覆盖更新失败：" + (job.message || ""), "warn");
          } else {
            finish(job.message || "已更新完成");
            toast(job.message || "已更新完成");
          }
        }
      } catch (e) { /* 忽略单次轮询错误 */ }
    }, 1500);
  }
