"""
Evaluation runner: executes test cases against the consultation system.
"""
from __future__ import annotations

import asyncio
import json
import logging
import uuid
from pathlib import Path
from typing import Any

from app.orchestrators.consultation import run_consultation_turn
from app.eval.evaluator import evaluate_case, generate_report, EvalReport

logger = logging.getLogger(__name__)

TEST_CASES_PATH = Path(__file__).parent / "test_cases.json"


def load_test_cases() -> list[dict]:
    """Load test cases from JSON file."""
    with open(TEST_CASES_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


async def run_single_case(case: dict, semaphore: asyncio.Semaphore) -> dict:
    """Run a single test case through the consultation system."""
    async with semaphore:
        case_id = case.get("id", "unknown")
        logger.info(f"Running test case: {case_id}")

        turns = case.get("turns", [])
        lang = case.get("lang", "zh")

        # Build messages from turns (only user messages trigger the system)
        messages = []
        response_text = ""
        actual_state = {}

        for turn in turns:
            if turn["role"] == "user":
                messages.append({"role": "user", "content": turn["content"]})

                try:
                    state = await asyncio.wait_for(
                        run_consultation_turn(
                            session_id=f"eval-{case_id}",
                            messages=messages,
                            current_status="INIT" if len(messages) == 1 else "COLLECTING",
                            round_count=len([m for m in messages if m["role"] == "user"]) - 1,
                            active_skills=[],
                            lang=lang,
                        ),
                        timeout=60,
                    )
                    response_text = state.get("latest_assistant_message", "")
                    actual_state = {
                        "status": state.get("status", ""),
                        "red_flag_detected": state.get("red_flag_detected", False),
                        "current_agent": state.get("current_agent", ""),
                        "round_count": state.get("round_count", 0),
                    }
                    messages.append({"role": "assistant", "content": response_text})

                except Exception as e:
                    logger.error(f"Test case {case_id} failed: {e}")
                    return {
                        "case_id": case_id,
                        "response_text": "",
                        "actual_state": {},
                        "error": str(e),
                    }

        return {
            "case_id": case_id,
            "response_text": response_text,
            "actual_state": actual_state,
            "error": None,
        }


async def run_evaluation(
    case_ids: list[str] | None = None,
    concurrency: int = 3,
) -> EvalReport:
    """Run evaluation on all or selected test cases.

    Args:
        case_ids: Optional list of specific case IDs to run. None = run all.
        concurrency: Max concurrent test case executions.

    Returns:
        EvalReport with scores and details.
    """
    run_id = str(uuid.uuid4())[:8]
    all_cases = load_test_cases()

    if case_ids:
        cases = [c for c in all_cases if c["id"] in case_ids]
    else:
        cases = all_cases

    semaphore = asyncio.Semaphore(concurrency)
    logger.info(f"Starting eval run {run_id} with {len(cases)} cases, concurrency={concurrency}")

    # Run all cases
    raw_results = await asyncio.gather(
        *[run_single_case(case, semaphore) for case in cases],
        return_exceptions=True,
    )

    # Evaluate results
    case_results = []
    for case, raw_result in zip(cases, raw_results):
        if isinstance(raw_result, Exception):
            from app.eval.evaluator import CaseResult, DimensionScore
            case_results.append(CaseResult(
                case_id=case.get("id", "unknown"),
                case_name=case.get("name", "Unknown"),
                passed=False,
                scores=[],
                overall_score=0.0,
                errors=[str(raw_result)],
            ))
        elif raw_result.get("error"):
            from app.eval.evaluator import CaseResult, DimensionScore
            case_results.append(CaseResult(
                case_id=raw_result["case_id"],
                case_name=case.get("name", "Unknown"),
                passed=False,
                scores=[],
                overall_score=0.0,
                errors=[raw_result["error"]],
            ))
        else:
            result = evaluate_case(
                case,
                raw_result["response_text"],
                raw_result["actual_state"],
            )
            case_results.append(result)

    report = generate_report(run_id, case_results)
    logger.info(f"Eval run {run_id} complete: {report.passed}/{report.total_cases} passed, avg={report.average_score}")
    return report
