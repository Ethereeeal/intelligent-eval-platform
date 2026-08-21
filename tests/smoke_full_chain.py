"""全链路冒烟：M01 → M02 → M03 → M04（打 Docker 后端）。

复用已有文档（含 M01 文档与 M02 EIU），跑：
- M02：确认 EIU 数据在
- M03：dry_run 批量计划 + 3 条 EIU 真实生成题目
- M04：对 corpus 全部已生成题目做一轮质量门禁
"""
from __future__ import annotations

import time

import httpx

BASE = "http://127.0.0.1:8000"
DOCUMENT_ID = 1  # 复用已有文档（含 存单质押 docx + 109 EIU）
client = httpx.Client(base_url=BASE, timeout=120)

PASS: list[bool] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    print(f"{'✅' if cond else '❌'} {name}" + (f" — {detail}" if detail else ""))
    PASS.append(cond)


print("=" * 60)
print("① M02：确认 EIU 数据")
eius = client.get("/api/eiu", params={"document_id": DOCUMENT_ID}).json()["items"]
check("M02 EIU 存在", len(eius) > 0, f"共 {len(eius)} 条")
questionable = [e for e in eius if e["is_questionable"]]
check("M02 可出题 EIU", len(questionable) >= 3, f"{len(questionable)} 条")

print()
print("② M03：dry_run 批量计划（不调 LLM）")
dry = client.post(
    "/api/cases/generate",
    params={"document_id": DOCUMENT_ID},
    json={"dry_run": True, "include_variations": False},
)
check("M03 dry_run 返回 200", dry.status_code == 200, f"status={dry.status_code}")
dry_body = dry.json()
if isinstance(dry_body, dict):
    planned = dry_body.get("planned", dry_body.get("items", dry_body))
    check("M03 dry_run 有计划清单", bool(planned), f"计划条数={len(planned) if planned else 0}")
else:
    check("M03 dry_run 有计划清单", bool(dry_body), f"dry_run 返回 {type(dry_body)} len={len(dry_body)}")

print()
print("③ M03：3 条 EIU 真实生成题目（DeepSeek）")
sample = questionable[:3]
for e in sample:
    t0 = time.time()
    r = client.post(
        f"/api/eiu/{e['eiu_id']}/generate-case",
        json={"angle": "primary", "include_variations": False},
    )
    ok = r.status_code == 200
    body = r.json() if ok else {}
    detail = body.get("case", body) if isinstance(body, dict) else {}
    check(
        f"EIU {e['eiu_id']} 生成题目",
        ok and (detail.get("case_id") or detail.get("question") or detail.get("id")),
        f"status={r.status_code} 耗时={time.time()-t0:.1f}s {str(detail)[:80]}",
    )
    time.sleep(0.5)  # 避免连发过密

cases = client.get("/api/cases", params={"document_id": DOCUMENT_ID}).json()
check("M03 已生成题目可查", len(cases) >= 3, f"共 {len(cases)} 题")

print()
print("④ M04：质量门禁（对已生成题目跑 5 项检查）")
t0 = time.time()
qr = client.post("/api/quality-check", params={"document_id": DOCUMENT_ID})
check("M04 quality-check 返回 200", qr.status_code == 200, f"status={qr.status_code} 耗时={time.time()-t0:.1f}s")
print("   summary:", str(qr.json())[:300])

results = client.get("/api/quality-check/results", params={"document_id": DOCUMENT_ID})
check("M04 结果汇总可查", results.status_code == 200, f"status={results.status_code}")

print()
print("=" * 60)
print(f"PASS: {sum(1 for c in PASS if c)} / {len(PASS)}")
