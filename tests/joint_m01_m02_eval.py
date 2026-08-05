"""M01 + M02 联合评估（打 Docker 后端 http://127.0.0.1:8000）。

流程：建语料库 → M01 上传真实 docx（解析+嵌入）→ M02 触发抽取 → 评估质量。
用法：
  python tests/joint_m01_m02_eval.py                      # 新建语料库并上传 docx
  python tests/joint_m01_m02_eval.py --corpus 1           # 复用已有语料库（跳过上传）
"""
from __future__ import annotations

import sys
import time
from collections import Counter

import httpx

BASE = "http://127.0.0.1:8000"
DOCX = (
    r"C:\Users\Kexin\Documents\xwechat_files\wxid_nabf5e0j4pl222_80f4\msg\file\2026-07"
    r"\10个产品文件\10个产品文件\附件1：上海银行单位定期存单质押授信业务操作规程（2025年版）.docx"
)

client = httpx.Client(base_url=BASE, timeout=180)

# 解析参数：--corpus N 复用已有语料库
REUSE_CORPUS: int | None = None
if len(sys.argv) >= 3 and sys.argv[1] == "--corpus":
    REUSE_CORPUS = int(sys.argv[2])

print("=" * 60)
if REUSE_CORPUS is not None:
    print("① M01 文档接入（复用已有语料库）")
    corpus_id = REUSE_CORPUS
    print(f"  语料库 corpus_id={corpus_id}")
    docs = client.get("/api/documents", params={"corpus_id": corpus_id}).json()
    document_id = docs[0]["document_id"]
    blocks = client.get(f"/api/documents/{document_id}/blocks").json()
    block_types = Counter(b["block_type"] for b in blocks)
    print(f"  文档: {docs[0]['file_name'][:50]} blocks={len(blocks)} 类型={dict(block_types)}")
    substantive = sum(1 for b in blocks if b["block_type"] != "title")
    print(f"  实质 Block（非标题）: {substantive}")
else:
    print("① M01 文档接入")
    # 1. 建语料库
    r = client.post("/api/corpus", json={"name": "存单质押-联合评估", "description": "M01+M02 联合测试"})
    r.raise_for_status()
    corpus_id = r.json()["corpus_id"]
    print(f"  语料库 corpus_id={corpus_id}")

    # 2. 上传真实 docx（M01：解析 + BGE 嵌入 + FAISS 索引）
    with open(DOCX, "rb") as f:
        r = client.post(
            "/api/documents/upload",
            data={"corpus_id": str(corpus_id), "upload_user": "acceptance"},
            files={"file": ("附件1：上海银行单位定期存单质押授信业务操作规程（2025年版）.docx", f, "application/vnd.openxmlformats-officedocument.wordprocessingml.document")},
        )
    r.raise_for_status()
    up = r.json()
    print(f"  上传结果: document_id={up.get('document_id')} duplicate={up.get('duplicate')} blocks={up.get('blocks')}")
    document_id = up["document_id"]

    doc = client.get(f"/api/documents/{document_id}").json()
    print(f"  parse_status={doc.get('parse_status')} status={doc.get('status')}")

    blocks = client.get(f"/api/documents/{document_id}/blocks").json()
    block_types = Counter(b["block_type"] for b in blocks)
    print(f"  Block 总数: {len(blocks)} | 类型分布: {dict(block_types)}")
    substantive = sum(1 for b in blocks if b["block_type"] != "title")
    print(f"  实质 Block（非标题）: {substantive}")

print()
print("② M02 EIU 抽取（DeepSeek 真实模型）")
r = client.post(f"/api/corpus/{corpus_id}/eiu/extract")
r.raise_for_status()
job_id = r.json()["job_id"]
print(f"  触发抽取 job_id={job_id} status={r.json()['status']}")

for _ in range(180):
    job = client.get(f"/api/jobs/{job_id}").json()
    if job["status"] in ("completed", "failed"):
        break
    time.sleep(1)
print(f"  Job 最终状态: {job['status']} | progress={job['progress']} | message={job['message']}")

if job["status"] != "completed":
    print("❌ 抽取失败，评估中止")
    sys.exit(1)

print()
print("③ M02 覆盖率报告")
coverage = client.get(f"/api/corpus/{corpus_id}/eiu/coverage").json()
print(f"  total_eiu={coverage['total_eiu']} questionable={coverage['questionable_eiu']} excluded={coverage['excluded_eiu']}")
print(f"  by_priority={coverage['by_priority']}")
print(f"  by_type={coverage['by_type']}")
print(f"  by_section({len(coverage['by_section'])}):")
for s in coverage["by_section"][:12]:
    print(f"    {s['section_path'][:36]:<38} {s['eiu_count']}")
rec = coverage["block_reconciliation"]
print(f"  block_reconciliation: {rec['covered_blocks']}/{rec['total_paragraph_blocks']} rate={rec['rate']}")
print(f"  weighted_coverage={coverage['weighted_coverage']} p0_coverage_pct={coverage['p0_coverage_pct']}")
print(f"  alerts={coverage['alerts']}")

print()
print("④ M02 数据质量检查（SPEC §9.2）")
eius = client.get(f"/api/corpus/{corpus_id}/eiu").json()["items"]
total = len(eius)
q = [e for e in eius if e["is_questionable"]]
excluded = [e for e in eius if not e["is_questionable"]]
by_prio = Counter(e["content_priority"] for e in q)
p0_ratio = by_prio.get("P0", 0) / len(q) if q else 0
types = {e["eiu_type"] for e in eius}

print(f"  D1 EIU≥Block×0.3:      {'✅' if total >= substantive * 0.3 else '❌'}  ({total} vs {substantive * 0.3:.1f})")
print(f"  D2 P0 占比 10%–40%:     {'✅' if 0.10 <= p0_ratio <= 0.40 else '❌'}  ({p0_ratio:.0%}, P0={by_prio.get('P0',0)}/{len(q)})")
print(f"  D3 类型≥5 种:           {'✅' if len(types) >= 5 else '❌'}  ({len(types)} 种 {sorted(types)})")
print(f"  D4 statement≤200 字:    {'✅' if all(len(e['statement']) <= 200 for e in eius) else '❌'}")
print(f"  D5 排除项必有理由:       {'✅' if all(bool(e['exclusion_reason']) for e in excluded) else '❌'}  (排除 {len(excluded)} 条)")
pairs = [(e["block_id"], e["statement"]) for e in eius]
print(f"  D6 无重复:              {'✅' if len(pairs) == len(set(pairs)) else '❌'}")
print(f"  F10 对账率 100%:         {'✅' if rec['rate'] == 1.0 else '❌'}")

print()
print("⑤ EIU 抽样（前 15 条，含章节）")
for e in eius[:15]:
    prio = e["content_priority"]
    marker = "" if e["is_questionable"] else f"[排除:{e['exclusion_reason']}]"
    print(f"    [{e['eiu_type']}/{prio}] {e['statement'][:48]} {marker}")

print()
print("⑥ 评估结论")
issues = []
if not (0.10 <= p0_ratio <= 0.40):
    issues.append(f"D2 P0 占比异常：{p0_ratio:.0%}")
if len(types) < 5:
    issues.append(f"D3 类型不足：{len(types)} 种")
if rec["rate"] < 1.0:
    issues.append(f"F10 对账率未达 100%：{rec['rate']:.0%}")
uncovered = rec.get("uncovered_blocks", [])
if uncovered:
    issues.append(f"未覆盖 Block：{[(u['block_id'], u['section_path']) for u in uncovered]}")
print("  " + ("；".join(issues) if issues else "全部检查项通过 ✅"))
