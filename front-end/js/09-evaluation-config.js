/* 评测方法与中间节点配置组件。 */
(() => {
  const taskProfileLabels = { question_answering: "通用问答", translation: "翻译", text_generation: "文本生成" };
  const methodOptions = [
    { id: "answer_comparison", label: "标准答案比对", note: "短答案精确匹配；长答案语义相似度", standard: "项目方法" },
    { id: "rules", label: "规则评测", note: "读取 must_have_points / acceptable_answers", standard: "项目方法" },
    { id: "llm_as_judge", label: "LLM-as-a-Judge", note: "使用自定义规则提示词进行判定", standard: "GB/T 45288.2—2025 第 6.5(c)（评测方法，非指标）" },
    { id: "bleu", label: "BLEU", note: "仅翻译任务可选；需要标准参考文本", standard: "GB/T 45288.2—2025 附录 A.1.5" },
    { id: "rouge_l", label: "ROUGE-L", note: "仅文本生成任务可选；需要标准参考文本", standard: "GB/T 45288.2—2025 附录 A.1.6" },
  ];
  const nodeOptions = [
    { id: "rewrite", label: "改写", note: "语义相似度；有约束标注时计算约束保持率及 P/R/F1" },
    { id: "intent", label: "意图识别", note: "Accuracy、Micro/Macro-F1、分类别 P/R/F1、混淆矩阵" },
    { id: "rag", label: "RAG", note: "RAGAS：Context Precision / Recall、Faithfulness、Answer Relevancy" },
  ];

  function createController({ state }) {
    const compatible = (method, profile) => method === "bleu" ? profile === "translation"
      : method === "rouge_l" ? profile === "text_generation" : true;

    function html() {
      const profile = state.taskProfile || "question_answering";
      const selected = new Set(state.evaluationMethods || []);
      const methods = methodOptions.map(item => {
        const disabled = !compatible(item.id, profile);
        const checked = !disabled && selected.has(item.id);
        return `<label class="ev-choice ${disabled ? "disabled" : ""}"><input type="checkbox" name="evMethod" value="${item.id}" ${checked ? "checked" : ""} ${disabled ? "disabled" : ""}/><span><b>${item.label}</b><small>${item.note}</small><em>${item.standard}</em></span></label>`;
      }).join("");
      const nodes = nodeOptions.map(item => `<label class="ev-choice"><input type="checkbox" name="evNode" value="${item.id}" ${(state.intermediateNodes || []).includes(item.id) ? "checked" : ""}/><span><b>${item.label}</b><small>${item.note}</small></span></label>`).join("");
      const judgeEnabled = selected.has("llm_as_judge");
      return `<div class="ev-eval-config-grid">
        <label class="es-field">本次任务类型<select class="es-input" id="evTaskProfile">${Object.entries(taskProfileLabels).map(([value, label]) => `<option value="${value}" ${profile === value ? "selected" : ""}>${label}</option>`).join("")}</select><small>一次运行只选择一种任务类型；混合任务请拆分运行。</small></label>
        <div class="ev-eval-group"><div class="ev-eval-group-title">评测方法 <small>可多选，并行输出独立结果</small></div><div class="ev-choice-grid">${methods}</div></div>
        <div class="ev-eval-group"><div class="ev-eval-group-title">中间过程节点 <small>可选；选中节点后使用固定指标组</small></div><div class="ev-choice-grid">${nodes}</div></div>
      </div>
      <div id="evJudgeFields" class="ev-judge-fields" ${judgeEnabled ? "" : "hidden"}>
        <label class="es-field">Judge 评测规则<textarea class="es-input" id="evJudgePrompt" rows="4" maxlength="10000" placeholder="写清楚判定标准、通过条件和评分规则"></textarea></label>
        <div class="ev-judge-context"><span>附加输入（按需勾选）</span><label><input type="checkbox" id="evJudgeHistory"/>多轮历史</label><label><input type="checkbox" id="evJudgeIntermediate"/>中间节点结果</label><label><input type="checkbox" id="evJudgeRetrieved"/>检索结果</label></div>
      </div>
      <p class="ev-standard-note">带“GB/T 45288.2—2025”标记的是引用标准公式或条文；该标注不表示本项目已通过国标认证。人工 MOS 评测暂未纳入。</p>`;
    }

    function bind() {
      const host = document.getElementById("evEvaluationControls");
      if (!host) return;
      const previousPrompt = host.querySelector("#evJudgePrompt");
      const previousContext = {
        history: host.querySelector("#evJudgeHistory")?.checked,
        intermediate: host.querySelector("#evJudgeIntermediate")?.checked,
        retrieved: host.querySelector("#evJudgeRetrieved")?.checked,
      };
      if (previousPrompt) state.judgePrompt = previousPrompt.value;
      for (const key of Object.keys(previousContext)) {
        if (previousContext[key] !== undefined) state.judgeContext[key] = previousContext[key];
      }
      host.innerHTML = html();
      const promptInput = host.querySelector("#evJudgePrompt");
      if (promptInput) {
        promptInput.value = state.judgePrompt || "";
        promptInput.oninput = () => { state.judgePrompt = promptInput.value; };
      }
      for (const key of Object.keys(state.judgeContext)) {
        const input = host.querySelector(`#evJudge${key[0].toUpperCase()}${key.slice(1)}`);
        if (input) {
          input.checked = Boolean(state.judgeContext[key]);
          input.onchange = () => { state.judgeContext[key] = input.checked; };
        }
      }
      host.querySelector("#evTaskProfile").onchange = event => {
        state.taskProfile = event.target.value;
        state.evaluationMethods = (state.evaluationMethods || []).filter(method => compatible(method, state.taskProfile));
        bind();
      };
      host.querySelectorAll("input[name=evMethod]").forEach(input => input.onchange = () => {
        state.evaluationMethods = [...host.querySelectorAll("input[name=evMethod]:checked")].map(item => item.value);
        bind();
      });
      host.querySelectorAll("input[name=evNode]").forEach(input => input.onchange = () => {
        state.intermediateNodes = [...host.querySelectorAll("input[name=evNode]:checked")].map(item => item.value);
      });
    }

    function read() {
      const methods = [...document.querySelectorAll("input[name=evMethod]:checked")].map(item => item.value);
      const nodes = [...document.querySelectorAll("input[name=evNode]:checked")].map(item => item.value);
      if (!methods.length && !nodes.length) throw new Error("至少选择一种评测方法或一个中间过程节点");
      const judgeEnabled = methods.includes("llm_as_judge");
      const prompt = document.getElementById("evJudgePrompt")?.value.trim() || "";
      if (judgeEnabled && !prompt) throw new Error("选择 LLM-as-a-Judge 后，请填写评测规则");
      return {
        task_profile: document.getElementById("evTaskProfile").value,
        evaluation_methods: methods,
        intermediate_eval: { enabled: nodes.length > 0, nodes },
        judge_eval: {
          enabled: judgeEnabled,
          prompt: judgeEnabled ? prompt : "",
          include_history: judgeEnabled && Boolean(document.getElementById("evJudgeHistory")?.checked),
          include_intermediate: judgeEnabled && Boolean(document.getElementById("evJudgeIntermediate")?.checked),
          include_retrieved: judgeEnabled && Boolean(document.getElementById("evJudgeRetrieved")?.checked),
        },
      };
    }

    return { taskProfileLabels, methodOptions, nodeOptions, bind, read };
  }

  window.EvaluationConfigUI = { createController };
})();
