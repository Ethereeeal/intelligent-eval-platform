(() => {
  const canvas = document.getElementById("overviewFlowCanvas");
  const toggle = document.getElementById("overviewFlowToggle");
  if (!canvas || !toggle) return;

  let mode = "evaluation";
  const refreshIcons = () => { if (window.lucide) window.lucide.createIcons(); };
  const evaluationMarkup = () => `
    <div class="flow-view flow-view-evaluation">
      <div class="eval-source-row">
        <div class="flow-mode-node source-upload"><span class="f-ic"><i data-lucide="upload"></i></span><b>上传评测集</b><small>经质量检测后入库</small></div>
        <button class="flow-mode-node source-generated" type="button" data-flow-toggle aria-label="查看生成评测集链路"><span class="f-ic"><i data-lucide="sparkles"></i></span><b>生成评测集</b><small>从文档生成并质检</small></button>
        <div class="flow-mode-node source-public"><span class="f-ic"><i data-lucide="badge-check"></i></span><b>公共评测库</b><small>内置通用维度题集</small></div>
      </div>
      <div class="flow-down" aria-hidden="true"><i data-lucide="arrow-down"></i></div>
      <div class="flow-result-node"><span class="f-ic"><i data-lucide="library-big"></i></span><b>评测集库</b><small>选择或合并后的可复用版本</small></div>
      <div class="flow-down" aria-hidden="true"><i data-lucide="arrow-down"></i></div>
      <div class="flow-run-node"><span class="f-ic"><i data-lucide="gauge"></i></span><b>自动评测</b><small>运行、评分与问题归因</small></div>
    </div>`;
  const generationMarkup = () => `
    <div class="flow-view flow-view-generation">
      <div class="generation-row">
        <div class="flow-linear-node"><span class="f-ic"><i data-lucide="file-text"></i></span><b>上传文档</b><small>解析与分块</small></div>
        <i data-lucide="arrow-right" class="flow-arrow" aria-hidden="true"></i>
        <div class="flow-linear-node"><span class="f-ic"><i data-lucide="list-checks"></i></span><b>知识点抽取</b><small>EIU 抽取与覆盖</small></div>
        <i data-lucide="arrow-right" class="flow-arrow" aria-hidden="true"></i>
        <button class="flow-linear-node flow-generated-trigger" type="button" data-flow-toggle aria-label="返回评测链路"><span class="f-ic"><i data-lucide="message-square-plus"></i></span><b>问答对生成</b><small>基于 EIU 生成样本</small></button>
        <i data-lucide="arrow-right" class="flow-arrow" aria-hidden="true"></i>
        <div class="flow-linear-node"><span class="f-ic"><i data-lucide="shield-check"></i></span><b>质量门禁</b><small>质检与人工复核</small></div>
        <i data-lucide="arrow-right" class="flow-arrow" aria-hidden="true"></i>
        <div class="flow-linear-node node-doc-set"><span class="f-ic"><i data-lucide="folder-check"></i></span><b>文档评测集</b><small>冻结的生成库版本</small></div>
      </div>
    </div>`;

  function bindNodeToggle() {
    canvas.querySelectorAll("[data-flow-toggle]").forEach((node) => {
      node.addEventListener("click", () => render(mode === "evaluation" ? "generation" : "evaluation"));
    });
  }
  function render(nextMode, animate = true) {
    if (animate) {
      canvas.classList.remove("is-visible");
      canvas.classList.add("is-transitioning", nextMode === "generation" ? "to-generation" : "to-evaluation");
    }
    window.setTimeout(() => {
      mode = nextMode;
      canvas.dataset.flow = mode;
      canvas.setAttribute("aria-label", mode === "evaluation" ? "评测链路" : "生成评测集链路");
      canvas.innerHTML = mode === "evaluation" ? evaluationMarkup() : generationMarkup();
      bindNodeToggle();
      refreshIcons();
      if (animate) requestAnimationFrame(() => canvas.classList.add("is-visible"));
      window.setTimeout(() => canvas.classList.remove("is-transitioning", "to-generation", "to-evaluation", "is-visible"), animate ? 430 : 0);
    }, animate ? 130 : 0);
  }
  toggle.addEventListener("click", (event) => {
    event.stopPropagation();
    render(mode === "evaluation" ? "generation" : "evaluation");
  });
  render("evaluation", false);
})();
