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

