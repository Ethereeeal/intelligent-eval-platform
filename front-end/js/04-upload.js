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
      preview: [], versions: [{ tag: "v1", note: `首次入库（上传至「${targetFull || TREE.name}」）`, time: "刚刚" }], kp: [], qa: [], review: [], parseProgress: 0 };
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
      const ex = await fetch(API_BASE + `/api/eiu/extract?document_id=${docId}`, { method: "POST" });
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
              // 4) 入库 + 知识点抽取完成：不自动生成问答对。
              //    EIU 已持久化在文档库，之后用户可在「问答对生成」界面手动选择该文档
              //    触发 m03 生成 + m04 质检；删掉旧问答对库后 EIU 仍在，可随时重新生成。
              await loadData();
              state.sel.doc = realId;
              renderLib("doc");
              renderLibContent("doc", realId);
              toast(`「${file.name}」已入库并抽取知识点，可在「问答对生成」界面手动生成问答对`);
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
    pollReuploadJob(res.job_id);
  }

  function pollReuploadJob(jobId) {
    const statusEl = document.createElement("div");
    statusEl.className = "up-reupload-status";
    statusEl.textContent = "覆盖更新中…";
    document.body.appendChild(statusEl);
    const finish = (msg, failed) => {
      statusEl.textContent = msg;
      statusEl.classList.toggle("err", !!failed);
      setTimeout(() => statusEl.remove(), 4000);
    };
    const poll = setInterval(async () => {
      try {
        const jr = await fetch(API_BASE + `/api/jobs/${jobId}`);
        if (!jr.ok) return;
        const job = await jr.json();
        if (job.progress != null) statusEl.textContent = `覆盖更新中 ${job.progress}%（${job.phase || ""}）`;
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

