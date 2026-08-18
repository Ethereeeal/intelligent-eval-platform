# 评测集评分策略依据（简要）

> 用途：为"评测集标准模板"与评分口径提供研究依据，独立于业务需求书。
> 状态：讨论收口稿，尚未并入 BRD。

## 1. 已确定的评分策略

### 单轮样本

模板字段：`q`（必填）、`a`（必填）、`evidence`（可选，无证据则降级标注）、`dimension`（可选）。

不含：同义答案、数值容差、预期行为、intent_id、corpus_id、内容优先级、数据集划分。

评分口径：

- 短答案（数值、日期、条款号、固定短语、拒答）→ 规范化精确匹配（去空白、全半角统一、数字格式标准化）；
- 自然语言长答案 → 语义相似度评分（embedding / 评分模型 + 阈值），阈值须经固定校准集验证；
- 评分策略为平台运行侧配置，不进模板字段。

### 多轮样本（可选模式）

- `session_id` + `turns[]`，最终轮 `a` 必填；
- 中间轮可标记 `key_turn`，测试类型 `memory`（记忆）或 `coherence`（连贯性）；
- `memory`：必须依赖前置轮信息，且该信息不得在关键轮问题中重复出现；
- `coherence`：必须声明 `depends_on_turns`，评分时检查与前置轮输出是否自相矛盾；
- 运行记录必须保存完整对话过程，用于归因。

## 2. 研究现状：三类主流评分范式

### 2.1 规则 / 词汇匹配（对应"短答案精确匹配"）

| 方法 | 适用 | 局限 |
|---|---|---|
| Exact Match / F1 | 短事实问答（SQuAD 等） | 与人类判断相关性低：EM 0.22、F1 0.40，LLM 裁判可达 0.85 |
| IFEval 可验证指令 | 指令遵循检查（字数、关键词、格式） | 只覆盖可枚举指令，不覆盖内容理解 |
| BLEU / ROUGE / 余弦相似度 | 翻译、摘要、开放式回答量化 | 词汇层面，对同义表述敏感 |

### 2.2 LLM-as-a-judge（对应"自然语言答案语义评分"）

- MT-Bench：GPT-4 裁判按 rubric 对多轮每一轮打 1–10 分，与人类偏好一致性 > 80%；明确存在位置偏差、冗长偏差、自我偏好；
- AlpacaEval 2.0：向裁判提供参考答案，以 win rate 计分，并用回归修正长度偏差；
- EMNLP 2025 综述：LLM 裁判不能作为唯一权威，须配合 rubric、校准与人工抽查。

### 2.3 分层 / 融合评分（对应"按答案形态分派策略"）

- COLING 2025：按场景分类，融合词汇匹配 + 语义指标 + LLM 裁判；先对长答案做摘要可显著提升评估效果。

## 3. 多轮评测依据（对应记忆 / 连贯性关键轮）

- MT-Bench：多轮基准，逐轮评分；
- Scale AI MultiChallenge：拆分为 `INFERENCE_MEMORY`（回忆并推理前文信息）与 `SELF_COHERENCE`（跨轮自洽）两个评测轴，与本项目关键轮设计对应；
- MT-Bench-101：量化 Memory Accuracy、Consistency Rate、Coherence Score 等指标。

## 4. 质量评估研究依据（EIU / QA / 评测集）

### 4.1 EIU 质量评估

无现成框架。"EIU"为项目自定义概念，但其六个指标均有对应的既有研究维度：

| 对话中的指标 | 对应研究维度 | 依据 |
|---|---|---|
| 完整性评分 | 数据完整性 completeness | 通用 AI 数据质量维度（准确、完整、一致、唯一、时效） |
| 独立性评分 | 可回答性 answerability / 自包含性 | 问题生成评测：不依赖额外上下文即可回答 |
| 信息密度 | 简洁性 conciseness | QGEval 的 conciseness 维度 |
| 重复率 | 唯一性 uniqueness / 去重 | 基准去重与污染研究 |
| 覆盖范围 | 覆盖率 coverage | 基准分析阶段的覆盖率检查 |
| 可生成 QA 比例 | 可回答性 answerability | 问题生成研究的 answerability 指标 |

### 4.2 QA 质量评估

- QGEval（EMNLP 2024）：问题生成多维评测基准，7 个标注维度：流畅性、清晰度、简洁性、相关性、一致性、可回答性、答案一致性；"清晰度、一致性、可回答性"对应本项目的"问题清晰度、问答一致性、有效 QA"；
- RubricBench（新加坡政府科技局）：4 个政府 AI 客服的 108 个问答对，按 14 个质量维度人工双标注，用于评测 LLM 裁判的多维评分能力，场景与本项目接近；
- NeuReg（2025）：监管合规领域神经符号 QA 生成，用 5 个指标人工评测 160 个问答对、共 4000 个评分，是监管领域 QA 质量评测的直接案例。

### 4.3 评测集质量评估

- How2Bench（港科大等，2025）：调研 2014–2024 年 274 个代码评测集，发布 55 项质量检查清单（设计、构建、评测、分析、发布五阶段）。关键发现：62% 未去重、近 80% 未处理数据泄漏、近七成无质量保障手段、18% 被下游评测集继承导致问题传播；论文明确清单可推广到问答、数学、推理类评测集；
- 泄漏/重复实证：SWE-bench 32.67% 的成功补丁涉及直接答案泄漏、31.08% 因测试用例不充分通过；MTEB 英文数据集 24% 存在泄漏；ICML 2025 污染研究用模糊字符串匹配对 4.4 万个基准问题去重；
- 由此支持本项目"上传评测集质量评估"四指标：数据完整率（completeness）、重复问题比例（uniqueness/去重）、有效 QA 比例（answerability + 一致性）、覆盖维度（coverage）。

### 4.4 结论

- 指标名称为项目自定，但每个指标对应的质量维度均有文献支撑；
- 评测集质量评估主流做法为三结合：规则检查（去重、字段完整性）+ 人工标注 rubric + LLM 裁判；
- 落地时需要把维度明确操作化（阈值、计算方法、评分主体），并在发布前做一次校准验证。

## 5. 对本项目评分策略的硬性要求

1. 短答案/数值 → 规范化精确匹配；自然语言答案 → 语义评分，不依赖字符串匹配；
2. 语义评分必须有 rubric 或参考答案参照，并用固定校准集验证阈值；
3. 采用 LLM 裁判时必须防位置偏差（交换顺序复评）与长度偏差（长度控制），并保留人工抽查；
4. 多轮记忆/连贯性采用"规则检查（关键信息是否出现、前后是否矛盾）+ LLM 裁判"结合，不只用字符串匹配；
5. 评分模型、阈值与版本必须记录，保证可复现、可解释。

## 6. 参考来源

1. Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena — https://arxiv.org/abs/2306.05685
2. Length-Controlled AlpacaEval — https://arxiv.org/abs/2404.04475
3. Instruction-Following Evaluation for Large Language Models (IFEval) — https://arxiv.org/abs/2311.07911
4. From Generation to Judgment: Opportunities and Challenges of LLM-as-a-judge — https://aclanthology.org/2025.emnlp-main.138/
5. Reassessing Extractive QA Datasets at Scale: LLM-as-a-Judge and In-Depth Analyses — https://ui.adsabs.harvard.edu/abs/2025arXiv250411972H/abstract
6. Multi-Layered Evaluation Using a Fusion of Metrics and LLMs as Judges in Open-Domain QA — https://aclanthology.org/2025.coling-main.408/
7. ScaleAI MultiChallenge — https://huggingface.co/datasets/ScaleAI/MultiChallenge
8. QGEval: Benchmarking Multi-dimensional Evaluation for Question Generation — https://arxiv.org/abs/2406.05707
9. RubricBench — https://huggingface.co/datasets/govtech/RubricBench
10. NeuReg: Neuro-Symbolic QA Generation from Regulatory Compliance — https://dl.acm.org/doi/10.1145/3731443.3771375
11. How2Bench: 代码评测集发展指南（55 项检查清单）— https://arxiv.org/abs/2501.10711
12. Forgetting Contamination（ICML 2025，基准问题去重）— https://github.com/tml-tuebingen/forgetting-contamination
