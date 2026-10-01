"""
issue_matcher.py — Orchestrates the full analysis pipeline:
analysis → retrieval → explanation → ranking → draft generation.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Optional

from embeddings import EmbeddingStore
from github_client import GitHubClient
from llm import OllamaClient
from readiness_score import (
    ReadinessFactors,
    compute_readiness_score,
    get_difficulty_from_combined,
    get_score_color,
    get_score_label,
)
from repo_analyzer import RepoAnalysis, RepoAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class AnalyzedIssue:
    """Fully analyzed issue with all derived data."""
    # Raw issue data
    number: int
    title: str
    body: str
    url: str
    labels: list[str]
    is_beginner_labeled: bool
    comment_count: int
    age_days: int
    is_assigned: bool

    # Derived analysis
    relevant_files: list[dict] = field(default_factory=list)  # from embeddings search
    explanation: str = ""           # LLM plain-language explanation
    fix_plan: str = ""              # LLM step-by-step plan
    readiness: Optional[ReadinessFactors] = None
    llm_score: int = 5              # LLM difficulty 1-10
    llm_difficulty: str = "medium"  # LLM difficulty label
    difficulty_label: str = ""      # Combined label
    composite_rank: float = 50.0    # Higher = easier
    draft_pr: Optional[dict] = None # Generated draft PR


class IssueMatcher:
    """
    Orchestrates all analysis steps to produce fully analyzed, ranked issues.
    """

    def __init__(
        self,
        github_client: GitHubClient,
        repo_analyzer: RepoAnalyzer,
        embedding_store: EmbeddingStore,
        llm_client: OllamaClient,
    ):
        self.gh = github_client
        self.analyzer = repo_analyzer
        self.embeddings = embedding_store
        self.llm = llm_client

    def analyze_issues(
        self,
        repo_analysis: RepoAnalysis,
        raw_issues: list[dict],
        gh_repo,  # PyGithub repo object
        progress_callback=None,
        n_relevant_files: int = 5,
    ) -> list[AnalyzedIssue]:
        """
        Full pipeline: for each issue, retrieve relevant files,
        explain, plan, score, and rank.
        
        Returns sorted list (easiest first).
        """
        if not raw_issues:
            return []

        total = len(raw_issues)
        analyzed: list[AnalyzedIssue] = []

        # ── Step 1: Get LLM rankings for all issues at once (batch) ──────────
        if progress_callback:
            progress_callback(f"LLM ranking {total} issues...")

        issues_summary = [
            {
                "number": iss["number"],
                "title": iss["title"],
                "body": iss["body"][:300],
                "labels": iss["labels"],
            }
            for iss in raw_issues
        ]
        repo_context = (
            f"{repo_analysis.repo_name}: "
            f"Languages: {', '.join(repo_analysis.languages.keys())}. "
            f"{repo_analysis.architecture_summary[:300]}"
        )
        llm_rankings = self.llm.rank_issues(issues_summary, repo_context)
        llm_rank_map = {r["number"]: r for r in llm_rankings}

        # ── Step 2: Per-issue analysis ────────────────────────────────────────
        for i, raw_issue in enumerate(raw_issues):
            issue_num = raw_issue["number"]
            if progress_callback:
                progress_callback(
                    f"Analyzing issue #{issue_num}: {raw_issue['title'][:50]}... "
                    f"({i+1}/{total})"
                )

            analyzed_issue = AnalyzedIssue(
                number=issue_num,
                title=raw_issue["title"],
                body=raw_issue["body"],
                url=raw_issue["url"],
                labels=raw_issue["labels"],
                is_beginner_labeled=raw_issue["is_beginner_labeled"],
                comment_count=raw_issue["comment_count"],
                age_days=raw_issue["age_days"],
                is_assigned=raw_issue["is_assigned"],
            )

            # Retrieve relevant files via semantic search
            search_query = f"{raw_issue['title']} {raw_issue['body'][:200]}"
            try:
                relevant = self.embeddings.search(
                    repo_analysis.repo_url,
                    search_query,
                    n_results=n_relevant_files,
                )
                analyzed_issue.relevant_files = relevant
            except Exception as e:
                logger.warning(f"Embedding search failed for issue #{issue_num}: {e}")
                relevant = []
                analyzed_issue.relevant_files = []

            # Compute recency and test coverage for relevant files
            relevant_paths = [r["path"] for r in relevant]
            recency_map = {}
            has_tests_map = {}
            for path in relevant_paths:
                try:
                    recency_map[path] = self.analyzer.compute_file_recency(
                        repo_analysis.clone_path, path
                    )
                except Exception:
                    recency_map[path] = 0
                has_tests_map[path] = self.analyzer.check_has_tests(
                    repo_analysis.files, path
                )

            # Compute readiness score
            analyzed_issue.readiness = compute_readiness_score(
                raw_issue, relevant_paths, recency_map, has_tests_map
            )

            # LLM ranking info
            llm_info = llm_rank_map.get(issue_num, {})
            analyzed_issue.llm_score = llm_info.get("llm_score", 5)
            analyzed_issue.llm_difficulty = llm_info.get("difficulty", "medium")

            # Combined difficulty label and rank
            analyzed_issue.difficulty_label, analyzed_issue.composite_rank = (
                get_difficulty_from_combined(
                    analyzed_issue.readiness.total_score,
                    analyzed_issue.llm_score,
                )
            )

            # LLM explanation (deferred — generated on expand in UI)
            # We pre-generate for top 5 to make UI snappy
            if i < 5:
                try:
                    analyzed_issue.explanation = self.llm.explain_issue(
                        issue_title=raw_issue["title"],
                        issue_body=raw_issue["body"],
                        issue_comments=raw_issue.get("comment_texts", []),
                        relevant_files=relevant,
                        repo_name=repo_analysis.repo_name,
                    )
                    analyzed_issue.fix_plan = self.llm.generate_fix_plan(
                        issue_title=raw_issue["title"],
                        issue_body=raw_issue["body"],
                        relevant_files=relevant,
                        repo_name=repo_analysis.repo_name,
                        architecture_context=repo_analysis.architecture_summary,
                    )
                except Exception as e:
                    logger.warning(f"LLM analysis failed for issue #{issue_num}: {e}")
                    analyzed_issue.explanation = "Analysis unavailable (LLM error)."
                    analyzed_issue.fix_plan = ""

            analyzed.append(analyzed_issue)

        # ── Step 3: Sort by composite rank (highest = easiest first) ─────────
        analyzed.sort(key=lambda x: x.composite_rank, reverse=True)

        return analyzed

    def get_issue_analysis_on_demand(
        self,
        issue: AnalyzedIssue,
        repo_analysis: RepoAnalysis,
        raw_issue: dict,
    ) -> AnalyzedIssue:
        """Generate explanation and fix plan on demand (for issues beyond top 5)."""
        if not issue.explanation:
            try:
                issue.explanation = self.llm.explain_issue(
                    issue_title=issue.title,
                    issue_body=issue.body,
                    issue_comments=raw_issue.get("comment_texts", []),
                    relevant_files=issue.relevant_files,
                    repo_name=repo_analysis.repo_name,
                )
            except Exception as e:
                issue.explanation = f"Analysis unavailable: {e}"

        if not issue.fix_plan:
            try:
                issue.fix_plan = self.llm.generate_fix_plan(
                    issue_title=issue.title,
                    issue_body=issue.body,
                    relevant_files=issue.relevant_files,
                    repo_name=repo_analysis.repo_name,
                    architecture_context=repo_analysis.architecture_summary,
                )
            except Exception as e:
                issue.fix_plan = f"Plan unavailable: {e}"

        return issue

    def generate_draft_pr(
        self,
        issue: AnalyzedIssue,
        repo_analysis: RepoAnalysis,
    ) -> dict:
        """Generate a draft PR for a selected issue."""
        # Load actual file contents for better stubs
        file_contents = {}
        for f in issue.relevant_files[:3]:
            path = f["path"]
            content = self.analyzer.get_file_content(repo_analysis.clone_path, path)
            file_contents[path] = content[:2000]  # Cap for LLM context

        return self.llm.generate_draft_pr(
            issue_title=issue.title,
            issue_body=issue.body,
            issue_number=issue.number,
            relevant_files=issue.relevant_files,
            repo_name=repo_analysis.repo_name,
            fix_plan=issue.fix_plan,
            file_contents=file_contents,
        )
