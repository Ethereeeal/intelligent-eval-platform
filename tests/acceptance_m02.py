"""M02 验收测试（真实 DeepSeek 模型）。

用法：`python tests/acceptance_m02.py`（在仓库根目录运行）
- 读取 demo/.env 中的 DeepSeek 配置（Key 仅写入环境变量，不打印）
- 功能验收 F1–F11（F12/F13 重试/JSON 修复另由本地 mock 验证）
- 数据质量验收 D1–D6（SPEC §9.2）
- 集成验收 I1–I4
"""
from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT))  # 使 `python tests/acceptance_m02.py` 可导入 modules.*

# ---- 读取 demo/.env（Key 仅写入环境变量，不打印）----
_demo_env: dict[str, str] = {}
_demo_env_path = REPO_ROOT / "demo" / ".env"
if _demo_env_path.exists():
    for line in _demo_env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        _demo_env[key.strip()] = value.strip().strip('"').strip("'")

LLM_URL = _demo_env.get("LLM_API_URL", "")
LLM_KEY = _demo_env.get("LLM_API_KEY", "")
assert LLM_URL and LLM_KEY, "demo/.env 缺少 LLM_API_URL / LLM_API_KEY"
LLM_BASE = re.sub(r"/chat/completions$", "", LLM_URL)

TEST_DB = REPO_ROOT / "storage" / "test_accept.db"
if TEST_DB.exists():
    TEST_DB.unlink()
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB.as_posix()}"
os.environ["LLM_API_BASE"] = LLM_BASE
os.environ["LLM_API_KEY"] = LLM_KEY
os.environ["LLM_MODEL"] = "deepseek-chat"
os.environ["LLM_TEMPERATURE"] = "0.0"
os.environ["LLM_MAX_TOKENS"] = "4096"

from fastapi.testclient import TestClient  # noqa: E402

from modules.shared.main import app  # noqa: E402
from modules.shared.services.database import DatabaseService  # noqa: E402

db = DatabaseService()
db.create_all()
corpus_id = db.save_corpus(name="存单质押操作规程验收库", description="真实模型验收")
document_id = db.save_document(
    corpus_id=corpus_id,
    file_name="单位定期存单质押贷款操作规程（2026年版）.docx",
    file_type=".docx",
    file_hash="acceptance-hash-001",
    minio_path="storage/raw/acceptance.docx",
)

# 真实银行规程风格测试文档（20 个实质段落 + 4 个标题 + 1 个过渡句）
blocks = [
    {"section_path": "第一章 总则", "block_type": "title", "block_text": "第一章 总则"},
    {"section_path": "第一章 总则", "block_type": "paragraph", "block_text": "本规程所称存单质押贷款，是指借款人以其本人或第三人合法持有的单位定期存单作为质押物，向我行申请的人民币贷款业务。"},
    {"section_path": "第一章 总则", "block_type": "paragraph", "block_text": "单位定期存单质押率原则上不得超过90%，且单笔贷款金额不得超过质押存单本息的90%。"},
    {"section_path": "第一章 总则", "block_type": "paragraph", "block_text": "存单质押贷款期限原则上不得超过一年。"},
    {"section_path": "第一章 总则", "block_type": "paragraph", "block_text": "不得接受他行开立的单位定期存单作为质押物。"},
    {"section_path": "第一章 总则", "block_type": "paragraph", "block_text": "由政策性担保机构提供全额担保的，质押率可放宽至95%。"},
    {"section_path": "第一章 总则", "block_type": "paragraph", "block_text": "本规程自2026年8月1日起施行，原《单位定期存单质押贷款操作规程（2023年版）》同时废止。"},
    {"section_path": "第二章 业务流程", "block_type": "title", "block_text": "第二章 业务流程"},
    {"section_path": "第二章 业务流程", "block_type": "paragraph", "block_text": "贷款流程：受理申请→调查核实→审批→签订合同→办理质押登记→发放贷款→贷后管理→贷款偿还。"},
    {"section_path": "第二章 业务流程", "block_type": "paragraph", "block_text": "授信调查人员应当对存单真实性、合法性及存款来源进行核实。"},
    {"section_path": "第二章 业务流程", "block_type": "paragraph", "block_text": "借款人应当按合同约定用途使用贷款资金，不得挪作他用。"},
    {"section_path": "第二章 业务流程", "block_type": "paragraph", "block_text": "2025年度全行存单质押贷款余额为1,280亿元，不良率为0.3%。"},
    {"section_path": "第二章 业务流程", "block_type": "paragraph", "block_text": "详见附件一（存单质押登记申请表样式）。"},
    {"section_path": "第二章 业务流程", "block_type": "paragraph", "block_text": "2026年版将质押率上限由85%调整为90%。"},
    {"section_path": "第三章 风险控制", "block_type": "title", "block_text": "第三章 风险控制"},
    {"section_path": "第三章 风险控制", "block_type": "paragraph", "block_text": "质押存单到期日不得早于贷款到期日。"},
    {"section_path": "第三章 风险控制", "block_type": "paragraph", "block_text": "出现以下情形时，银行应当要求借款人追加担保：质押物价值明显下降、质押存单到期、借款人信用状况恶化。"},
    {"section_path": "第三章 风险控制", "block_type": "paragraph", "block_text": "质押存单挂失后的解押，应当凭法院判决书或执行裁定书办理。"},
    {"section_path": "第四章 贷后管理", "block_type": "title", "block_text": "第四章 贷后管理"},
    {"section_path": "第四章 贷后管理", "block_type": "paragraph", "block_text": "各行应当建立健全存单质押贷款风险管理制度。"},
    {"section_path": "第四章 贷后管理", "block_type": "paragraph", "block_text": "存单质押贷款应当纳入全行统一授信管理。"},
    {"section_path": "第四章 贷后管理", "block_type": "paragraph", "block_text": "贷款利率按照人民银行有关规定和本行定价政策执行。"},
    {"section_path": "第四章 贷后管理", "block_type": "paragraph", "block_text": "借款人在还款能力允许的前提下可以申请提前还款。"},
    {"section_path": "第四章 贷后管理", "block_type": "paragraph", "block_text": "本规程未尽事宜，按照我行相关管理规定执行。"},
]
db.save_blocks(document_id=document_id, blocks=blocks)

PASS: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    status = "✅" if cond else "❌"
    print(f"{status} {name}" + (f" — {detail}" if detail else ""))
    PASS.append(cond)


# ----------------------------------------------------------------------
# I1 / I2 / I4：后端启动、health、路由注册
# ----------------------------------------------------------------------
with TestClient(app) as client:
    check("I1 后端启动无报错", True)
    health = client.get("/health").json()
    check("I2 /health 返回 OK", health.get("status") == "ok")

    # F1：触发真实模型抽取
    resp = client.post(f"/api/corpus/{corpus_id}/eiu/extract")
    check("F1 抽取触发返回 202 + job_id", resp.status_code == 202 and resp.json().get("job_id"))
    job_id = resp.json()["job_id"]

    for _ in range(180):  # 最多等 180s
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] in ("completed", "failed"):
            break
        time.sleep(1)
    check("F2 真实模型抽取任务完成", job["status"] == "completed", f"job={job}")
    check("F2 progress=100", job["progress"] == 100)

    # F3 / F4：清单与过滤
    listing = client.get(f"/api/corpus/{corpus_id}/eiu").json()
    eius = listing["items"]
    total = listing["total"]
    check("F3 EIU 列表返回", total > 0, f"total={total}")
    p0_only = client.get(f"/api/corpus/{corpus_id}/eiu", params={"priority": "P0"}).json()
    check("F3 priority 过滤", all(e["content_priority"] == "P0" for e in p0_only["items"]))
    type_filter = client.get(
        f"/api/corpus/{corpus_id}/eiu",
        params=[("type", "threshold"), ("type", "prohibition")],
    ).json()
    check("F4 type 复合过滤", all(e["eiu_type"] in ("threshold", "prohibition") for e in type_filter["items"]))

    # 数据质量 D1–D6
    from collections import Counter

    substantive = sum(1 for b in blocks if b["block_type"] != "title")
    check("D1 EIU ≥ 实质Block×0.3", total >= substantive * 0.3, f"{total} vs {substantive * 0.3:.1f}")

    by_priority = Counter(e["content_priority"] for e in eius if e["is_questionable"])
    q_total = sum(by_priority.values())
    p0_ratio = by_priority.get("P0", 0) / q_total if q_total else 0
    check("D2 P0 占比 10%–40%", 0.10 <= p0_ratio <= 0.40, f"P0={by_priority.get('P0', 0)}/{q_total}={p0_ratio:.0%}")

    type_count = len({e["eiu_type"] for e in eius})
    check("D3 EIU 类型 ≥ 5 种", type_count >= 5, f"types={type_count} {sorted({e['eiu_type'] for e in eius})}")

    check("D4 statement ≤ 200 字", all(len(e["statement"]) <= 200 for e in eius))
    excluded = [e for e in eius if not e["is_questionable"]]
    check("D5 排除项必有 exclusion_reason", all(bool(e["exclusion_reason"]) for e in excluded), f"excluded={len(excluded)}")
    pairs = [(e["block_id"], e["statement"]) for e in eius]
    check("D6 无重复 EIU", len(pairs) == len(set(pairs)))

    # F8 / F10：覆盖率（删除操作前检查，对账率应为 100%）
    coverage = client.get(f"/api/corpus/{corpus_id}/eiu/coverage").json()
    for key in ("by_priority", "by_type", "by_document", "by_section", "weighted_coverage", "p0_coverage_pct", "block_reconciliation"):
        check(f"F8 coverage 含 {key}", key in coverage)
    rec = coverage["block_reconciliation"]
    check("F10 Block 对账率 100%（抽取后）", rec["rate"] == 1.0, f"rate={rec['rate']}, covered={rec['covered_blocks']}/{rec['total_paragraph_blocks']}")
    check("coverage by_document 含文档名", len(coverage["by_document"]) >= 1 and coverage["by_document"][0].get("document_name"), f"by_document={coverage['by_document']}")

    # F5–F7 / F9
    first = eius[0]
    detail = client.get(f"/api/eiu/{first['eiu_id']}").json()
    check("F5 详情含原文上下文", bool(detail.get("context") and detail["context"].get("block_text")))

    updated = client.put(f"/api/eiu/{first['eiu_id']}", json={"content_priority": "P1"}).json()
    check("F6 手动编辑成功 + 权重重算", updated["weight"] == 3)
    bad = client.put(f"/api/eiu/{first['eiu_id']}", json={"content_priority": "P9"})
    check("F6 非法优先级 422", bad.status_code == 422)

    deleted = client.delete(f"/api/eiu/{first['eiu_id']}").json()
    check("F7 删除标记 blocked", deleted["review_status"] == "blocked")

    gaps = client.get(f"/api/corpus/{corpus_id}/eiu/gaps").json()
    check("F9 未覆盖清单", gaps["total"] > 0, f"gaps={gaps['total']}")

    # F11：空语料库
    empty_corpus = db.save_corpus(name="空库")
    empty_resp = client.post(f"/api/corpus/{empty_corpus}/eiu/extract")
    check("F11 空语料库不报错", empty_resp.status_code == 202 and "无可处理的段落" in empty_resp.json()["message"])

print("\n" + "=" * 50)
print(f"PASS: {sum(1 for c in PASS if c)} / {len(PASS)}")
print("模型:", os.environ["LLM_MODEL"], "| 端点:", LLM_BASE)
if all(PASS):
    print("M02 真实模型验收全部通过 ✅")
else:
    print("存在未通过项 ❌")
