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
    const typeMap = { pdf: "PDF", docx: "DOCX", doc: "DOC", txt: "TXT", md: "MD" };
    const type = typeMap[ext] || ext.toUpperCase() || "FILE";
    const kb = file.size / 1024;
    const size = kb >= 1024 ? (kb / 1024).toFixed(1) + " MB" : Math.max(1, Math.round(kb)) + " KB";
    // folderPath：完整目标目录路径（含系统目录根，如「基础问题输入文档/子A/子B」）；缺省按 purpose 落到系统目录根
    const targetFull = folderPath || "";
    const rootName = targetFull.split("/")[0] || (state._uploadPurpose === "gen" ? "仅泛化输入文档" : "基础问题输入文档");
    const purpose = state._uploadPurpose && !targetFull
      ? state._uploadPurpose
      : (rootName === "仅泛化输入文档" ? "gen" : "basic");
    state._uploadPurpose = null;
    state._uploadFolderPath = null;
    const relPath = targetFull.replace(/^[^/]+\/?/, ""); // 去掉系统目录根后的相对子路径

    DOCS[id] = { name: file.name, type, size, status: "上传中…", ver: "v1", updated: "刚刚",
      preview: [], versions: [{ tag: "v1", note: `首次入库（上传至「${targetFull || rootName}」）`, time: "刚刚" }], kp: [], qa: [], review: [], parseProgress: 0 };
    insertDocIntoFolderTree(purpose, relPath, id, file.name);

    renderLib("doc");
    state.sel.doc = id;
    renderLibContent("doc", id);
    const tr = $(`#docTree .tree-row[data-doc="${id}"]`);
    if (tr) { $$("#docTree .tree-row.active").forEach(x => x.classList.remove("active")); tr.classList.add("active"); }

    try {
      // 0) 按所选系统目录（purpose）上传，后端强制文档归属 basic/gen 两系统目录之一，不可游离到其它位置

      // 1) 上传到后端（归属所选系统目录；folder_path 保留目录结构层级）
      const fd = new FormData();
      fd.append("purpose", purpose);
      if (targetFull) fd.append("folder_path", targetFull);
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
              // 4) 单文档问答对生成：仅当前文档，不混库、不重抽其他文档
              toast(`「${file.name}」知识点已抽取，正在生成问答对…`);
              try {
                const gq = await fetch(
                  API_BASE + `/api/cases/generate?document_id=${docId}`,
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

