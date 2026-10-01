"""
readiness_score.py — Computes a transparent, multi-factor Contribution Readiness Score per issue.

Score is 0–100 combining:
  - Files touched count  (fewer files = better for beginners)
  - Has existing tests   (easier to verify = better)
  - File recency         (actively-changing files = riskier)
  - Issue freshness      (very old or already assigned = lower)
  - Issue clarity        (body length as proxy)
"""
from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass
class ReadinessFactors:
    """All factors contributing to the readiness score, for transparency."""
    files_count: int          # Number of files likely touched
    has_tests: bool           # At least one relevant file has tests
    avg_recency_commits: float  # Avg commits in last 90 days (across relevant files)
    issue_age_days: int
    is_assigned: bool
    comment_count: int
    is_beginner_labeled: bool
    issue_body_length: int    # Proxy for clarity (longer = clearer)
    
    # Computed sub-scores (0-100 each)
    scope_score: float = 0.0
    test_score: float = 0.0
    stability_score: float = 0.0
    freshness_score: float = 0.0
    clarity_score: float = 0.0
    total_score: float = 0.0

    # Human-readable explanations
    scope_label: str = ""
    test_label: str = ""
    stability_label: str = ""
    freshness_label: str = ""
    clarity_label: str = ""


# Weight of each factor in final score (must sum to 1.0)
WEIGHTS = {
    "scope": 0.30,      # How many files to touch
    "tests": 0.20,      # Has test coverage → verifiable
    "stability": 0.20,  # How actively changing → risk
    "freshness": 0.20,  # Issue age and assignment status
    "clarity": 0.10,    # Issue description quality
}


def compute_readiness_score(
    issue: dict,
    relevant_files: list[str],
    recency_map: dict[str, int],   # filepath → commit count in 90 days
    has_tests_map: dict[str, bool], # filepath → has tests
) -> ReadinessFactors:
    """
    Compute a fully transparent readiness score for one issue.
    
    Args:
        issue: enriched issue dict from github_client
        relevant_files: list of file paths likely touched (from embedding retrieval)
        recency_map: {filepath: commits_in_90_days}
        has_tests_map: {filepath: bool}
    
    Returns:
        ReadinessFactors with all sub-scores and labels set
    """
    f = ReadinessFactors(
        files_count=len(relevant_files),
        has_tests=any(has_tests_map.get(p, False) for p in relevant_files),
        avg_recency_commits=_avg(
            [recency_map.get(p, 0) for p in relevant_files]
        ) if relevant_files else 0.0,
        issue_age_days=issue.get("age_days", 0),
        is_assigned=issue.get("is_assigned", False),
        comment_count=issue.get("comment_count", 0),
        is_beginner_labeled=issue.get("is_beginner_labeled", False),
        issue_body_length=len(issue.get("body", "")),
    )

    # ── Scope Score (fewer files = better) ──────────────────────────────────
    n = f.files_count
    if n == 0 or n == 1:
        f.scope_score = 100
        f.scope_label = f"Touches ~{max(n,1)} file (very focused)"
    elif n <= 3:
        f.scope_score = 75
        f.scope_label = f"Touches ~{n} files (manageable)"
    elif n <= 6:
        f.scope_score = 45
        f.scope_label = f"Touches ~{n} files (moderate scope)"
    else:
        f.scope_score = max(10, 100 - (n * 10))
        f.scope_label = f"Touches ~{n} files (broad scope — harder)"

    # ── Test Score (existing tests = verifiable) ─────────────────────────────
    if f.has_tests:
        f.test_score = 100
        f.test_label = "Relevant files have tests ✓ (easy to verify your fix)"
    else:
        f.test_score = 30
        f.test_label = "No existing tests found (harder to verify — you may need to write tests)"

    # ── Stability Score (less churn = safer to modify) ───────────────────────
    avg_c = f.avg_recency_commits
    if avg_c == 0:
        f.stability_score = 100
        f.stability_label = "Files are stable (0 recent commits) — low merge conflict risk"
    elif avg_c <= 2:
        f.stability_score = 80
        f.stability_label = f"Files changed ~{avg_c:.1f}x recently — low churn"
    elif avg_c <= 8:
        f.stability_score = 50
        f.stability_label = f"Files changed ~{avg_c:.1f}x recently — moderate churn"
    else:
        f.stability_score = max(10, 100 - avg_c * 5)
        f.stability_label = f"Files changed ~{avg_c:.1f}x recently — high churn, merge conflict risk"

    # ── Freshness Score (open but not stale, unassigned) ─────────────────────
    age = f.issue_age_days
    freshness = 100

    # Age penalty: issues over 180 days old may be stale or deprioritized
    if age > 365:
        freshness -= 40
    elif age > 180:
        freshness -= 20
    elif age > 90:
        freshness -= 10

    # Already assigned: someone else may be working on it
    if f.is_assigned:
        freshness -= 30
        
    # High comment count may mean it's contested or complex
    if f.comment_count > 15:
        freshness -= 20
    elif f.comment_count > 8:
        freshness -= 10

    # Bonus for beginner label
    if f.is_beginner_labeled:
        freshness += 10

    f.freshness_score = max(0, min(100, freshness))
    labels = []
    if age > 180:
        labels.append("old issue")
    if f.is_assigned:
        labels.append("already assigned")
    if f.comment_count > 10:
        labels.append("many comments")
    if f.is_beginner_labeled:
        labels.append("beginner-labeled ✓")
    f.freshness_label = (", ".join(labels) or "Fresh issue") + f" ({age}d old)"

    # ── Clarity Score (issue description quality) ────────────────────────────
    body_len = f.issue_body_length
    if body_len > 500:
        f.clarity_score = 90
        f.clarity_label = "Well-described issue (detailed body)"
    elif body_len > 150:
        f.clarity_score = 65
        f.clarity_label = "Adequately described"
    elif body_len > 30:
        f.clarity_score = 40
        f.clarity_label = "Sparse description — may need to ask questions"
    else:
        f.clarity_score = 15
        f.clarity_label = "Very sparse description — unclear requirements"

    # ── Total Weighted Score ─────────────────────────────────────────────────
    f.total_score = round(
        f.scope_score     * WEIGHTS["scope"]
        + f.test_score      * WEIGHTS["tests"]
        + f.stability_score * WEIGHTS["stability"]
        + f.freshness_score * WEIGHTS["freshness"]
        + f.clarity_score   * WEIGHTS["clarity"],
        1,
    )

    return f


def get_score_color(score: float) -> str:
    """Map score to a color for UI display."""
    if score >= 75:
        return "#22c55e"   # Green
    elif score >= 50:
        return "#f59e0b"   # Amber
    elif score >= 30:
        return "#f97316"   # Orange
    else:
        return "#ef4444"   # Red


def get_score_label(score: float) -> str:
    """Map score to a human label."""
    if score >= 75:
        return "🟢 Excellent"
    elif score >= 55:
        return "🟡 Good"
    elif score >= 35:
        return "🟠 Moderate"
    else:
        return "🔴 Challenging"


def get_difficulty_from_combined(
    readiness_score: float,
    llm_score: int,
) -> tuple[str, float]:
    """
    Combine readiness score and LLM judgment into a final difficulty label + rank.
    
    Returns: (difficulty_label, composite_rank_score)
    Where composite_rank_score is higher = easier.
    """
    # Normalize: readiness 0-100, llm_score 1-10 (lower = easier)
    # Convert llm_score to 0-100 where higher = easier
    llm_ease = (10 - llm_score) * 10  # 0 = hardest, 90 = easiest

    # Weighted composite (readiness = ground truth, llm = contextual)
    composite = 0.6 * readiness_score + 0.4 * llm_ease

    if composite >= 70:
        return "✅ Great First Issue", composite
    elif composite >= 50:
        return "👍 Good for Beginners", composite
    elif composite >= 30:
        return "⚠️ Moderate Difficulty", composite
    else:
        return "🔥 Advanced", composite


def _avg(values: list) -> float:
    if not values:
        return 0.0
    return sum(values) / len(values)
