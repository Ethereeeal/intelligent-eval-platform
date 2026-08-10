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

