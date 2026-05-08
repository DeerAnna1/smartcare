"""评估框架 API"""
import json
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from app.eval.runner import run_evaluation, load_test_cases

router = APIRouter(prefix="/eval", tags=["评估框架"])


class EvalRunRequest(BaseModel):
    case_ids: list[str] | None = None
    concurrency: int = 3


class EvalRunResponse(BaseModel):
    run_id: str
    total_cases: int
    passed: int
    failed: int
    average_score: float
    dimension_averages: dict[str, float]
    case_results: list[dict]


@router.post("/run", response_model=EvalRunResponse)
async def trigger_eval_run(body: EvalRunRequest):
    """触发一次评估运行。返回评估报告。"""
    try:
        report = await asyncio.wait_for(
            run_evaluation(
                case_ids=body.case_ids,
                concurrency=body.concurrency,
            ),
            timeout=300,
        )
    except asyncio.TimeoutError:
        raise HTTPException(status_code=504, detail="评估运行超时（5分钟限制）")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"评估运行失败: {e}")

    case_results = []
    for cr in report.case_results:
        case_results.append({
            "case_id": cr.case_id,
            "case_name": cr.case_name,
            "passed": cr.passed,
            "overall_score": cr.overall_score,
            "scores": [{"name": s.name, "score": s.score, "details": s.details} for s in cr.scores],
            "response_preview": cr.response_text[:200],
            "errors": cr.errors,
        })

    return EvalRunResponse(
        run_id=report.run_id,
        total_cases=report.total_cases,
        passed=report.passed,
        failed=report.failed,
        average_score=report.average_score,
        dimension_averages=report.dimension_averages,
        case_results=case_results,
    )


@router.get("/cases")
async def list_test_cases():
    """列出所有测试用例。"""
    cases = load_test_cases()
    return [
        {
            "id": c["id"],
            "name": c["name"],
            "description": c.get("description", ""),
            "lang": c.get("lang", "zh"),
            "turn_count": len(c.get("turns", [])),
        }
        for c in cases
    ]
