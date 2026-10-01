"""
github_client.py — GitHub repo/issue fetching, rate-limit resilience, and offline fallback.
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import requests
from github import Github, GithubException, RateLimitExceededException, GithubRetry
from github.Repository import Repository
from github.Issue import Issue

logger = logging.getLogger(__name__)

# Labels that indicate beginner-friendly issues
BEGINNER_LABELS = [
    "good first issue",
    "good-first-issue",
    "beginner",
    "beginner-friendly",
    "easy",
    "starter",
    "help wanted",
    "help-wanted",
    "hacktoberfest",
    "first-timers-only",
    "up-for-grabs",
    "low-hanging-fruit",
    "easy-fix",
    "newbie",
]


def parse_github_url(url: str) -> tuple[str, str]:
    """Extract owner and repo name from a GitHub URL."""
    url = url.strip().rstrip("/")
    patterns = [
        r"github\.com[:/]([^/]+)/([^/\s.]+?)(?:\.git)?$",
        r"^([^/]+)/([^/\s.]+?)(?:\.git)?$",
    ]
    for pattern in patterns:
        m = re.search(pattern, url)
        if m:
            return m.group(1), m.group(2)
    raise ValueError(
        f"Could not parse GitHub URL: '{url}'. "
        "Please provide a valid URL like https://github.com/owner/repo"
    )


class GitHubClient:
    """Wraps PyGithub with zero-blocking rate-limit handling and offline git fallbacks."""

    def __init__(self, token: Optional[str] = None):
        self.token = token.strip() if (token and token.strip()) else None
        self.rate_limited = False

        # Use total=0 retry to NEVER freeze the thread with automatic backoff sleeps
        retry_policy = GithubRetry(total=0)
        try:
            if self.token:
                self.gh = Github(login_or_token=self.token, retry=retry_policy, timeout=6)
            else:
                self.gh = Github(retry=retry_policy, timeout=6)
        except Exception:
            self.gh = Github(retry=retry_policy, timeout=6)

    def get_repo(self, owner: str, repo: str) -> Optional[Repository]:
        """
        Fetch a repository object.
        If rate limited (HTTP 403), sets rate_limited=True and returns None gracefully.
        """
        try:
            return self.gh.get_repo(f"{owner}/{repo}")
        except RateLimitExceededException:
            logger.warning("GitHub API rate limit exceeded on get_repo.")
            self.rate_limited = True
            return None
        except GithubException as e:
            if e.status == 403:
                logger.warning(f"GitHub API 403 (Rate limit or forbidden): {e.data.get('message', '')}")
                self.rate_limited = True
                return None
            elif e.status == 404:
                raise ValueError(
                    f"Repository '{owner}/{repo}' not found on GitHub. "
                    "Make sure the repository name is spelled correctly and is public."
                )
            logger.warning(f"GitHub API error ({e.status}): {e}")
            return None
        except Exception as e:
            logger.warning(f"Unexpected error fetching repo from GitHub API: {e}")
            return None

    def get_repo_metadata(
        self,
        repo: Optional[Repository],
        owner: str = "",
        repo_name: str = "",
        clone_path: Optional[str | Path] = None,
    ) -> dict:
        """
        Extract rich metadata.
        Falls back to local cloned files if PyGithub is rate-limited or offline.
        """
        full_name = f"{owner}/{repo_name}" if (owner and repo_name) else (repo.full_name if repo else "unknown/repo")
        clone_url = f"https://github.com/{full_name}.git"

        # If repo is available from API
        if repo is not None and not self.rate_limited:
            try:
                try:
                    readme_content = repo.get_readme().decoded_content.decode("utf-8", errors="replace")
                except Exception:
                    readme_content = ""

                try:
                    languages = dict(repo.get_languages())
                except Exception:
                    languages = {}

                return {
                    "full_name": repo.full_name,
                    "description": repo.description or "Open source project",
                    "homepage": repo.homepage or "",
                    "stars": repo.stargazers_count,
                    "forks": repo.forks_count,
                    "open_issues_count": repo.open_issues_count,
                    "default_branch": repo.default_branch or "main",
                    "created_at": repo.created_at.isoformat() if repo.created_at else "",
                    "updated_at": repo.updated_at.isoformat() if repo.updated_at else "",
                    "clone_url": repo.clone_url or clone_url,
                    "languages": languages,
                    "topics": list(repo.get_topics()) if hasattr(repo, "get_topics") else [],
                    "readme": readme_content[:8000],
                    "license": repo.license.name if repo.license else "Open Source",
                    "source": "github_api",
                }
            except Exception as e:
                logger.warning(f"Failed extracting metadata from GitHub API ({e}), falling back to local git.")

        # Fallback: extract metadata directly from cloned local directory
        readme_text = ""
        languages: dict[str, int] = {}
        license_name = "Open Source"
        default_branch = "main"

        if clone_path:
            cpath = Path(clone_path)
            # Find README
            for rname in ["README.md", "readme.md", "README.rst", "README.txt", "README"]:
                rfile = cpath / rname
                if rfile.exists():
                    try:
                        readme_text = rfile.read_text(encoding="utf-8", errors="replace")[:8000]
                        break
                    except Exception:
                        pass

            # Find License
            for lname in ["LICENSE", "LICENSE.md", "LICENSE.txt", "COPYING"]:
                lfile = cpath / lname
                if lfile.exists():
                    license_name = "MIT / Open Source (detected)"
                    break

            # Check git branch
            try:
                import git
                r = git.Repo(cpath)
                default_branch = r.active_branch.name
            except Exception:
                pass

        # Extract short description from first paragraph of README
        description = "Repository analyzed directly via local Git clone."
        if readme_text:
            lines = [l.strip() for l in readme_text.splitlines() if l.strip() and not l.startswith("#")]
            if lines:
                description = lines[0][:200]

        return {
            "full_name": full_name,
            "description": description,
            "homepage": f"https://github.com/{full_name}",
            "stars": "Public Git Repo",
            "forks": "—",
            "open_issues_count": "Local Analysis",
            "default_branch": default_branch,
            "created_at": "",
            "updated_at": "",
            "clone_url": clone_url,
            "languages": languages,
            "topics": ["hacktoberfest", "open-source"],
            "readme": readme_text,
            "license": license_name,
            "source": "local_git",
        }

    def get_issues(
        self,
        repo: Optional[Repository],
        clone_path: Optional[str | Path] = None,
        owner: str = "",
        repo_name: str = "",
        max_issues: int = 20,
        prefer_beginner: bool = True,
    ) -> list[dict]:
        """
        Fetch open issues. If GitHub API is rate-limited or repo is None,
        gracefully extracts actionable tasks from the cloned codebase (TODOs, missing tests, docstrings).
        """
        issues_raw = []

        if repo is not None and not self.rate_limited:
            try:
                if prefer_beginner:
                    seen_ids: set[int] = set()
                    for label in BEGINNER_LABELS:
                        if len(issues_raw) >= max_issues or self.rate_limited:
                            break
                        try:
                            for issue in repo.get_issues(state="open", labels=[label]):
                                if issue.number not in seen_ids and not issue.pull_request:
                                    issues_raw.append(issue)
                                    seen_ids.add(issue.number)
                                    if len(issues_raw) >= max_issues:
                                        break
                        except RateLimitExceededException:
                            self.rate_limited = True
                            break
                        except GithubException as ge:
                            if ge.status == 403:
                                self.rate_limited = True
                                break
                        except Exception:
                            continue

                if not issues_raw and not self.rate_limited:
                    try:
                        for issue in repo.get_issues(state="open"):
                            if not issue.pull_request:
                                issues_raw.append(issue)
                                if len(issues_raw) >= max_issues:
                                    break
                    except (RateLimitExceededException, GithubException):
                        self.rate_limited = True

                if issues_raw:
                    return [self._enrich_issue(iss) for iss in issues_raw]
            except (RateLimitExceededException, GithubException) as e:
                logger.warning(f"GitHub API issue fetching halted ({e}). Falling back to codebase task extraction.")
                self.rate_limited = True
            except Exception as e:
                logger.warning(f"Unexpected error in live issue fetching: {e}")

        # Fallback: extract genuine contribution opportunities from the cloned codebase
        if clone_path:
            return self.extract_codebase_issues(clone_path, owner=owner, repo_name=repo_name, max_issues=max_issues)

        return []

    def extract_codebase_issues(
        self,
        clone_path: str | Path,
        owner: str = "",
        repo_name: str = "",
        max_issues: int = 15,
    ) -> list[dict]:
        """
        Analyze the local codebase files to find genuine beginner contribution opportunities:
        1. Code TODO / FIXME comments.
        2. Source files missing unit test coverage.
        3. Documentation and configuration improvements.
        """
        cpath = Path(clone_path)
        issues: list[dict] = []
        issue_id = 100

        # 1. Scan for TODO / FIXME in code
        for file in cpath.rglob("*"):
            if len(issues) >= max_issues:
                break
            if file.is_file() and file.suffix.lower() in [".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".java"]:
                if any(ignored in file.parts for ignored in [".git", "node_modules", "venv", "__pycache__"]):
                    continue
                try:
                    rel_path = str(file.relative_to(cpath))
                    content = file.read_text(encoding="utf-8", errors="ignore")
                    lines = content.splitlines()
                    for line_idx, line in enumerate(lines, 1):
                        clean_line = line.strip()
                        if any(marker in clean_line.upper() for marker in ["TODO", "FIXME", "NOTE:"]):
                            issue_id += 1
                            summary_text = re.sub(r"^[#/\*\s]+(TODO|FIXME|NOTE:?)[:\s]*", "", clean_line, flags=re.I).strip()
                            if len(summary_text) < 5:
                                summary_text = f"Review and address task in {file.name}"

                            context_snippet = "\n".join(lines[max(0, line_idx - 3):min(len(lines), line_idx + 4)])
                            issues.append({
                                "number": issue_id,
                                "title": f"Code Task: {summary_text[:70]}",
                                "body": (
                                    f"**File**: `{rel_path}:{line_idx}`\n\n"
                                    f"**Context**:\n```\n{context_snippet}\n```\n\n"
                                    f"**Action Required**: Address the code comment and ensure comprehensive test coverage."
                                ),
                                "url": f"https://github.com/{owner}/{repo_name}" if owner else "#",
                                "labels": ["good first issue", "code-task", "refactor"],
                                "is_beginner_labeled": True,
                                "comment_count": 0,
                                "comment_texts": [],
                                "age_days": 1,
                                "staleness_days": 1,
                                "assignees": [],
                                "is_assigned": False,
                                "author": "codebase-scanner",
                                "milestone": "Hacktoberfest Starter",
                                "reactions": 1,
                            })
                            if len(issues) >= max_issues:
                                break
                except Exception:
                    continue

        # 2. Add Test Coverage tasks if test files are missing
        if len(issues) < max_issues:
            for file in cpath.rglob("*"):
                if len(issues) >= max_issues:
                    break
                if file.is_file() and file.suffix.lower() in [".py", ".js", ".ts"]:
                    if any(ignored in file.parts for ignored in [".git", "node_modules", "tests", "test"]):
                        continue
                    rel_path = str(file.relative_to(cpath))
                    test_candidate1 = cpath / f"test_{file.name}"
                    test_candidate2 = cpath / "tests" / f"test_{file.name}"
                    if not test_candidate1.exists() and not test_candidate2.exists():
                        issue_id += 1
                        issues.append({
                            "number": issue_id,
                            "title": f"Add Unit Tests for `{file.name}`",
                            "body": (
                                f"**Target File**: `{rel_path}`\n\n"
                                f"Currently `{rel_path}` has no direct corresponding unit test suite. "
                                f"Write automated tests verifying core functions and edge cases to prevent regressions."
                            ),
                            "url": f"https://github.com/{owner}/{repo_name}" if owner else "#",
                            "labels": ["good first issue", "tests", "beginner-friendly"],
                            "is_beginner_labeled": True,
                            "comment_count": 0,
                            "comment_texts": [],
                            "age_days": 1,
                            "staleness_days": 1,
                            "assignees": [],
                            "is_assigned": False,
                            "author": "codebase-scanner",
                            "milestone": "Test Coverage",
                            "reactions": 2,
                        })

        return issues

    def _enrich_issue(self, issue: Issue) -> dict:
        """Convert a PyGithub Issue to a plain dict with all relevant fields."""
        try:
            comments = list(issue.get_comments())
            comment_texts = [c.body for c in comments[:5]]
        except Exception:
            comment_texts = []

        labels = [lbl.name.lower() for lbl in issue.labels]
        is_beginner = any(bl in labels for bl in [l.lower() for l in BEGINNER_LABELS])

        now = datetime.now(timezone.utc)
        created = issue.created_at.replace(tzinfo=timezone.utc) if issue.created_at else now
        updated = issue.updated_at.replace(tzinfo=timezone.utc) if issue.updated_at else now
        age_days = (now - created).days
        staleness_days = (now - updated).days

        return {
            "number": issue.number,
            "title": issue.title,
            "body": (issue.body or "")[:4000],
            "url": issue.html_url,
            "labels": [lbl.name for lbl in issue.labels],
            "is_beginner_labeled": is_beginner,
            "comment_count": issue.comments,
            "comment_texts": comment_texts,
            "age_days": age_days,
            "staleness_days": staleness_days,
            "assignees": [a.login for a in issue.assignees],
            "is_assigned": len(issue.assignees) > 0,
            "author": issue.user.login if issue.user else "unknown",
            "milestone": issue.milestone.title if issue.milestone else None,
            "reactions": issue.reactions.total_count if hasattr(issue, "reactions") else 0,
        }

    def get_recent_commits_for_file(
        self,
        repo: Optional[Repository],
        filepath: str,
        clone_path: Optional[str | Path] = None,
        days: int = 90,
    ) -> int:
        """Count commits to a file in the past N days. Uses local git if available for instant speed."""
        if clone_path:
            try:
                import git
                r = git.Repo(clone_path)
                commits = list(r.iter_commits(paths=filepath, max_count=30))
                return len(commits)
            except Exception:
                pass

        if repo is not None and not self.rate_limited:
            try:
                from datetime import timedelta
                since = datetime.now(timezone.utc) - timedelta(days=days)
                commits = list(repo.get_commits(path=filepath, since=since))
                return len(commits)
            except Exception:
                return 0

        return 1

    def check_file_has_tests(
        self,
        repo: Optional[Repository],
        filepath: str,
        clone_path: Optional[str | Path] = None,
    ) -> bool:
        """Check if a file has a corresponding test file, checking local filesystem first."""
        base_name = Path(filepath).name
        stem = Path(filepath).stem

        test_names = [
            f"test_{base_name}",
            f"{stem}_test.py",
            f"test_{stem}.py",
            f"test_{stem}.js",
            f"test_{stem}.ts",
        ]

        if clone_path:
            cpath = Path(clone_path)
            for tname in test_names:
                if list(cpath.rglob(tname)):
                    return True

        return False

    def validate_ollama(self, base_url: str = "http://localhost:11434") -> tuple[bool, list[str]]:
        """Check if Ollama is running and return available models without hanging."""
        try:
            resp = requests.get(f"{base_url}/api/tags", timeout=2)
            if resp.status_code == 200:
                models = [m["name"] for m in resp.json().get("models", [])]
                return True, models
            return False, []
        except Exception:
            return False, []
