"""
Evaluation framework for the consultation multi-agent system.
Scores each test case across multiple dimensions.
"""
from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class DimensionScore:
    name: str
    score: float  # 0.0 - 1.0
    details: str = ""


@dataclass
class CaseResult:
    case_id: str
    case_name: str
    passed: bool
    scores: list[DimensionScore] = field(default_factory=list)
    overall_score: float = 0.0
    response_text: str = ""
    actual_state: dict = field(default_factory=dict)
    errors: list[str] = field(default_factory=list)


@dataclass
class EvalReport:
    run_id: str
    total_cases: int
    passed: int
    failed: int
    average_score: float
    case_results: list[CaseResult] = field(default_factory=list)
    dimension_averages: dict[str, float] = field(default_factory=dict)


def score_triage(expected: dict, actual_state: dict, response_text: str) -> DimensionScore:
    """Score triage level accuracy."""
    expected_level = expected.get("triage_level")
    if not expected_level:
        return DimensionScore(name="triage_accuracy", score=1.0, details="No triage level expected")

    # Check response text for triage level indicators
    actual_level = actual_state.get("status", "")
    response_lower = response_text.lower()

    # Check for emergency indicators
    emergency_keywords = ["急诊", "emergency", "urgent", "紧急", "立即就医"]
    outpatient_keywords = ["门诊", "outpatient", "就诊"]
    observe_keywords = ["观察", "observe", "注意"]

    detected_level = "observe"
    if any(kw in response_lower for kw in emergency_keywords):
        detected_level = "emergency"
    elif any(kw in response_lower for kw in outpatient_keywords):
        detected_level = "outpatient"
    elif any(kw in response_lower for kw in observe_keywords):
        detected_level = "observe"

    # Also check if the response contains triage JSON
    json_match = None
    import re
    m = re.search(r'"triage_level"\s*:\s*"([^"]+)"', response_text)
    if m:
        detected_level = m.group(1)

    if expected_level == detected_level:
        return DimensionScore(name="triage_accuracy", score=1.0, details=f"Correct: {detected_level}")
    elif expected_level == "emergency" and detected_level in ("urgent_visit", "emergency"):
        return DimensionScore(name="triage_accuracy", score=0.8, details=f"Close: expected {expected_level}, got {detected_level}")
    elif expected_level == "outpatient" and detected_level in ("outpatient", "observe"):
        return DimensionScore(name="triage_accuracy", score=0.7, details=f"Acceptable: expected {expected_level}, got {detected_level}")
    else:
        return DimensionScore(name="triage_accuracy", score=0.0, details=f"Mismatch: expected {expected_level}, got {detected_level}")


def score_risk_detection(expected: dict, response_text: str) -> DimensionScore:
    """Score red flag / risk detection accuracy."""
    expected_red_flag = expected.get("red_flag", False)
    response_lower = response_text.lower()

    # Check for risk indicators in response
    high_risk_indicators = ["紧急", "急诊", "立即", "emergency", "urgent", "危险", "高风险"]
    detected_risk = any(indicator in response_lower for indicator in high_risk_indicators)

    if expected_red_flag == detected_risk:
        return DimensionScore(name="risk_detection", score=1.0, details="Risk detection correct")
    elif expected_red_flag and detected_risk:
        return DimensionScore(name="risk_detection", score=0.8, details="Both flagged risk (partial match)")
    elif expected_red_flag and not detected_risk:
        return DimensionScore(name="risk_detection", score=0.0, details="Missed red flag")
    else:
        return DimensionScore(name="risk_detection", score=0.5, details="False positive risk flag")


def score_symptom_completeness(expected: dict, response_text: str) -> DimensionScore:
    """Score symptom information completeness."""
    if not expected.get("has_symptoms"):
        return DimensionScore(name="symptom_completeness", score=1.0, details="No symptom check needed")

    # Check if response acknowledges and discusses symptoms
    symptom_indicators = ["症状", "symptom", "持续", "duration", "严重", "severity"]
    found_count = sum(1 for ind in symptom_indicators if ind in response_text.lower())

    min_expected = expected.get("min_symptom_count", 1)
    score = min(1.0, found_count / (min_expected + 1))

    return DimensionScore(
        name="symptom_completeness",
        score=score,
        details=f"Found {found_count} symptom indicators"
    )


def score_department_suggestion(expected: dict, response_text: str) -> DimensionScore:
    """Score department recommendation accuracy."""
    expected_depts = expected.get("department_keywords", [])
    if not expected_depts:
        return DimensionScore(name="department_suggestion", score=1.0, details="No department check needed")

    response_lower = response_text.lower()
    found = any(dept in response_lower for dept in expected_depts)

    if found:
        return DimensionScore(name="department_suggestion", score=1.0, details=f"Found department match")
    else:
        return DimensionScore(name="department_suggestion", score=0.0, details=f"Missing department: {expected_depts}")


def score_response_quality(response_text: str) -> DimensionScore:
    """Score general response quality."""
    if not response_text or len(response_text.strip()) < 10:
        return DimensionScore(name="response_quality", score=0.0, details="Response too short or empty")

    score = 0.5  # Base score for having content

    # Bonus for reasonable length
    if 20 < len(response_text) < 2000:
        score += 0.2

    # Bonus for structured response
    if any(marker in response_text for marker in ["。", ".", "！", "!", "？", "?"]):
        score += 0.1

    # Bonus for medical professionalism (not definitive diagnosis)
    negative_indicators = ["确诊", "诊断为", "你得了", "you have been diagnosed"]
    if not any(neg in response_text.lower() for neg in negative_indicators):
        score += 0.2

    return DimensionScore(name="response_quality", score=min(1.0, score), details=f"Quality score: {score:.2f}")


def score_tool_usage(expected: dict, actual_state: dict, tool_runs: list[dict] | None = None) -> DimensionScore:
    """Score whether the correct tool was called.

    Args:
        expected: Expected outcomes from test case.
        actual_state: Actual state from consultation run.
        tool_runs: List of tool invocation records, each with keys:
            - tool_name: str
            - result_status: str ("success" / "failed")
            - request_json: str (JSON params)
    """
    expected_tool = expected.get("tool_called")
    if not expected_tool:
        return DimensionScore(name="tool_usage", score=1.0, details="No tool check needed")

    runs = tool_runs or []

    # Filter runs matching the expected tool name
    matching_runs = [r for r in runs if r.get("tool_name") == expected_tool]

    if not matching_runs:
        # Expected tool was not called at all
        any_runs = [r.get("tool_name") for r in runs]
        if any_runs:
            return DimensionScore(
                name="tool_usage", score=0.0,
                details=f"Expected tool '{expected_tool}' not called; got: {any_runs}"
            )
        return DimensionScore(
            name="tool_usage", score=0.0,
            details=f"Expected tool '{expected_tool}' not called; no tool invocations recorded"
        )

    # Check if any matching run succeeded
    successful = [r for r in matching_runs if r.get("result_status") == "success"]
    if successful:
        return DimensionScore(
            name="tool_usage", score=1.0,
            details=f"Tool '{expected_tool}' called and succeeded"
        )

    # Tool was called but failed
    return DimensionScore(
        name="tool_usage", score=0.3,
        details=f"Tool '{expected_tool}' called but all runs failed"
    )


def evaluate_case(case: dict, response_text: str, actual_state: dict, tool_runs: list[dict] | None = None) -> CaseResult:
    """Evaluate a single test case against expected outcomes."""
    expected = case.get("expected", {})
    case_id = case.get("id", "unknown")
    case_name = case.get("name", "Unknown")

    scores = [
        score_triage(expected, actual_state, response_text),
        score_risk_detection(expected, response_text),
        score_symptom_completeness(expected, response_text),
        score_department_suggestion(expected, response_text),
        score_response_quality(response_text),
        score_tool_usage(expected, actual_state, tool_runs),
    ]

    # Weighted average
    weights = {
        "triage_accuracy": 0.25,
        "risk_detection": 0.25,
        "symptom_completeness": 0.15,
        "department_suggestion": 0.10,
        "response_quality": 0.15,
        "tool_usage": 0.10,
    }

    total_weight = sum(weights.get(s.name, 0.1) for s in scores)
    overall = sum(s.score * weights.get(s.name, 0.1) for s in scores) / total_weight if total_weight > 0 else 0.0

    # Pass threshold: 0.6
    passed = overall >= 0.6

    return CaseResult(
        case_id=case_id,
        case_name=case_name,
        passed=passed,
        scores=scores,
        overall_score=round(overall, 3),
        response_text=response_text[:500],
        actual_state=actual_state,
    )


def generate_report(run_id: str, case_results: list[CaseResult]) -> EvalReport:
    """Generate a summary report from all case results."""
    total = len(case_results)
    passed = sum(1 for r in case_results if r.passed)
    failed = total - passed
    avg_score = sum(r.overall_score for r in case_results) / total if total > 0 else 0.0

    # Dimension averages
    dim_totals: dict[str, list[float]] = {}
    for r in case_results:
        for s in r.scores:
            dim_totals.setdefault(s.name, []).append(s.score)
    dim_avgs = {name: round(sum(vals) / len(vals), 3) for name, vals in dim_totals.items()}

    return EvalReport(
        run_id=run_id,
        total_cases=total,
        passed=passed,
        failed=failed,
        average_score=round(avg_score, 3),
        case_results=case_results,
        dimension_averages=dim_avgs,
    )
