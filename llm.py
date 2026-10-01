"""
llm.py — All Ollama prompt logic, streaming output, and low-temperature consistency.
"""
from __future__ import annotations

import json
import logging
from typing import Generator, Optional

import requests

logger = logging.getLogger(__name__)

DEFAULT_TEMPERATURE = 0.1  # Low for consistency
DEFAULT_TIMEOUT = 120


class OllamaClient:
    """Manages all LLM interactions via Ollama REST API, with fallback demo mode."""

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        model: str = "qwen2.5-coder:7b",
        temperature: float = DEFAULT_TEMPERATURE,
        demo_mode: bool = False,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.demo_mode = demo_mode

    def _post(self, endpoint: str, payload: dict, stream: bool = False, timeout: int = DEFAULT_TIMEOUT):
        """Raw POST to Ollama API."""
        url = f"{self.base_url}{endpoint}"
        try:
            resp = requests.post(url, json=payload, stream=stream, timeout=timeout)
            resp.raise_for_status()
            return resp
        except requests.exceptions.ConnectionError:
            raise RuntimeError(
                "Cannot connect to Ollama. Make sure Ollama is running: `ollama serve`"
            )
        except requests.exceptions.Timeout:
            raise RuntimeError(
                f"Ollama request timed out after {timeout}s. "
                "Try a smaller model (qwen2.5-coder:3b) or reduce context size."
            )
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 404:
                raise RuntimeError(
                    f"Model '{self.model}' not found in Ollama. "
                    f"Run: `ollama pull {self.model}`"
                )
            raise RuntimeError(f"Ollama API error: {e}")

    def generate(self, prompt: str, system: str = "", max_tokens: int = 2048) -> str:
        """Non-streaming generation. Returns full response text."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": False,
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        resp = self._post("/api/generate", payload, stream=False, timeout=DEFAULT_TIMEOUT)
        return resp.json().get("response", "")

    def generate_stream(
        self, prompt: str, system: str = "", max_tokens: int = 2048
    ) -> Generator[str, None, None]:
        """Streaming generation. Yields text chunks as they arrive."""
        payload = {
            "model": self.model,
            "prompt": prompt,
            "stream": True,
            "options": {
                "temperature": self.temperature,
                "num_predict": max_tokens,
            },
        }
        if system:
            payload["system"] = system

        resp = self._post("/api/generate", payload, stream=True)
        for line in resp.iter_lines():
            if line:
                try:
                    data = json.loads(line)
                    token = data.get("response", "")
                    if token:
                        yield token
                    if data.get("done", False):
                        break
                except json.JSONDecodeError:
                    continue

    # ─────────────────────────────────────────────
    #  High-Level Prompt Methods
    # ─────────────────────────────────────────────

    def explain_architecture(
        self,
        repo_name: str,
        readme: str,
        file_tree: list[str],
        languages: dict,
        entry_points: list[str],
        key_files_summary: str,
    ) -> Generator[str, None, None]:
        """Stream a plain-language architecture explanation."""
        lang_str = ", ".join(f"{k} ({v} files)" for k, v in sorted(languages.items(), key=lambda x: -x[1])[:5])

        if self.demo_mode:
            summary = (
                f"### 📦 Architecture Overview: {repo_name}\n\n"
                f"**1. What this project does:**\n"
                f"{repo_name} provides robust, modular tools and libraries built primarily in {lang_str or 'Python'}.\n\n"
                f"**2. Codebase Structure:**\n"
                f"- **Entry Points & Core Modules:** {', '.join(entry_points[:4]) if entry_points else 'Top-level source package'}\n"
                f"- **Total Files Tracked:** {len(file_tree)} files across key modules and utilities\n"
                f"- **Key Components:**\n{key_files_summary[:600] if key_files_summary else '- Core application modules'}\n\n"
                f"**3. Key Frameworks & Technologies:**\n"
                f"- Primary languages: {lang_str}\n"
                f"- Standardized module layout with decoupled layers\n\n"
                f"**4. How Data & Requests Flow:**\n"
                f"Commands and function calls enter through entry points or public API functions, traverse parsing/validation routines, pass through internal helpers, and return structured outcomes or objects.\n\n"
                f"**5. Recommended Starting Points for Hacktoberfest Contributors:**\n"
                f"- Review `README.md` and test suites to see expected behaviors.\n"
                f"- Explore `{entry_points[0] if entry_points else (file_tree[0] if file_tree else 'main')}` for the primary entry pattern.\n"
                f"- Check documentation and unit tests for bite-sized starter PRs.\n"
            )
            for chunk in summary.split("\n"):
                yield chunk + "\n"
            return
        tree_sample = "\n".join(file_tree[:60])
        if len(file_tree) > 60:
            tree_sample += f"\n... and {len(file_tree)-60} more files"

        system = (
            "You are an expert open-source mentor explaining codebases to first-time contributors. "
            "Be clear, friendly, and avoid jargon. Use markdown formatting."
        )
        prompt = f"""Analyze this GitHub repository and write a beginner-friendly architecture overview.

## Repository: {repo_name}

### README (excerpt):
{readme[:3000]}

### Languages: {lang_str}

### File Tree (sample):
```
{tree_sample}
```

### Entry Points: {', '.join(entry_points) if entry_points else 'Not detected'}

### Key Files Summary:
{key_files_summary[:3000]}

---
Write a clear, structured architecture explanation covering:
1. **What this project does** (1-2 sentences, plain English)
2. **How it's structured** (main directories and their purposes)
3. **Key frameworks & technologies** used
4. **How data/requests flow** through the system (entry point → key layers → output)
5. **Good starting points** for a new contributor to read first

Keep it friendly and accessible to someone new to the codebase."""

        yield from self.generate_stream(prompt, system=system, max_tokens=1500)

    def explain_issue(
        self,
        issue_title: str,
        issue_body: str,
        issue_comments: list[str],
        relevant_files: list[dict],
        repo_name: str,
    ) -> str:
        """Explain what an issue is asking for in plain language."""
        if self.demo_mode:
            target = relevant_files[0]['path'] if relevant_files else "codebase files"
            return (
                f"### 💡 Issue Explanation: {issue_title}\n\n"
                f"**1. What's the problem?**\n"
                f"The issue requests an update or fix for `{issue_title}`. "
                f"Specifically, logic associated with `{target}` requires adjustment to handle expected behaviors.\n\n"
                f"**2. Why does it matter?**\n"
                f"Addressing this improves project reliability, resolves developer ambiguity, and aligns functionality with project standards.\n\n"
                f"**3. What needs to change?**\n"
                f"- Locate the relevant function or configuration in `{target}`.\n"
                f"- Update the implementation to handle the described edge case or feature request.\n"
                f"- Run and expand unit test coverage.\n\n"
                f"**4. Complexity Assessment**\n"
                f"**Beginner-Friendly**: High. Focused scope with clear expected results."
            )

        files_ctx = "\n\n".join(
            f"### {f['path']}\n```\n{f['content'][:800]}\n```"
            for f in relevant_files[:4]
        )
        comments_ctx = "\n".join(f"- {c[:300]}" for c in issue_comments[:3])

        system = "You are a senior developer helping a first-time contributor understand an issue. Be specific and concrete."
        prompt = f"""Repository: {repo_name}
Issue: #{issue_title}

Issue description:
{issue_body[:2000]}

Recent comments:
{comments_ctx or 'No comments yet.'}

Most relevant source files:
{files_ctx}

---
Explain this issue clearly for a beginner:
1. **What's the problem?** (in plain English, 2-3 sentences)
2. **Why does it matter?** (user impact or technical impact)
3. **What needs to change?** (specific, concrete description)
4. **Complexity assessment**: Is this truly beginner-friendly? Any hidden complexity?"""

        return self.generate(prompt, system=system, max_tokens=800)

    def generate_fix_plan(
        self,
        issue_title: str,
        issue_body: str,
        relevant_files: list[dict],
        repo_name: str,
        architecture_context: str,
    ) -> str:
        """Generate a numbered step-by-step fix plan."""
        if self.demo_mode:
            target = relevant_files[0]['path'] if relevant_files else "the target module"
            return (
                f"### 🛠️ Step-by-Step Fix Plan for: {issue_title}\n\n"
                f"**Step 1: Set Up & Isolate Environment**\n"
                f"- Fork the repository on GitHub and clone locally.\n"
                f"- Create a dedicated branch: `git checkout -b fix/issue-update`\n"
                f"- Run existing test suites to establish a working baseline.\n\n"
                f"**Step 2: Understand the Code & Entry Point**\n"
                f"- Open `{target}` and inspect functions referenced by the issue.\n"
                f"- Check how input parameters or configurations are validated.\n\n"
                f"**Step 3: Implement Minimal, Focused Changes**\n"
                f"- Apply the fix in `{target}` following prevailing style and lint conventions.\n"
                f"- Avoid incidental refactoring; keep changes strictly scoped to the issue.\n\n"
                f"**Step 4: Verify with Tests**\n"
                f"- Add a unit test verifying both the happy path and edge cases.\n"
                f"- Run the test runner locally (`pytest` or equivalent) to confirm all tests pass.\n\n"
                f"**Step 5: Submit Pull Request**\n"
                f"- Commit changes with a conventional commit message referencing the issue number.\n"
                f"- Submit the PR with the generated draft template."
            )

        files_ctx = "\n\n".join(
            f"### {f['path']}\nFunctions: {f['metadata'].get('functions', '')}\n"
            f"```\n{f['content'][:600]}\n```"
            for f in relevant_files[:5]
        )

        system = "You are an expert mentor creating actionable fix plans for open-source contributors. Be specific, numbered, and concrete."
        prompt = f"""Repository: {repo_name}
Issue: {issue_title}

Issue description:
{issue_body[:1500]}

Architecture context:
{architecture_context[:1000]}

Relevant files:
{files_ctx}

---
Create a concrete, numbered step-by-step plan to fix this issue:

**Step 1: Set Up**
- Fork and clone the repo
- Install dependencies

**Step 2: Understand the code**
- Which specific files/functions to read first
- What they currently do

**Step 3-N: Make the changes**
- Exactly which file(s) to modify
- What to add/change/remove
- Code patterns to follow from existing code

**Final steps:**
- How to test the fix
- What to include in the PR description

Be specific about file names and function names. A beginner should be able to follow this without guessing."""

        return self.generate(prompt, system=system, max_tokens=1200)

    def rank_issues(
        self,
        issues_summary: list[dict],
        repo_context: str,
    ) -> list[dict]:
        """
        Ask LLM to rank issues by difficulty and return structured assessment.
        Returns list of {issue_number, difficulty_label, reasoning, llm_score}.
        """
        if self.demo_mode:
            rankings = []
            for iss in issues_summary:
                labels = [l.lower() for l in iss.get("labels", [])]
                is_easy = any(b in labels for b in ["good first issue", "easy", "beginner", "documentation", "docs", "starter", "help wanted"])
                score = 2 if is_easy else (4 if len(iss.get("body", "")) > 100 else 6)
                diff = "easy" if score <= 3 else ("medium" if score <= 6 else "hard")
                rankings.append({
                    "number": iss["number"],
                    "difficulty": diff,
                    "llm_score": score,
                    "reasoning": "Heuristic assessment based on issue labels, title, and body complexity.",
                })
            return rankings

        issues_text = "\n".join(
            f"Issue #{iss['number']}: {iss['title']}\n"
            f"Labels: {', '.join(iss['labels'])}\n"
            f"Body: {iss['body'][:300]}\n"
            for iss in issues_summary
        )

        system = "You are evaluating GitHub issues for first-time contributors. Be objective and consistent."
        prompt = f"""Repository context: {repo_context[:500]}

Issues to rank (from easiest to hardest for a first-time contributor):
{issues_text}

For each issue, respond in JSON format only. Return a JSON array where each object has:
- "number": the issue number (integer)
- "difficulty": one of "trivial", "easy", "medium", "hard"  
- "llm_score": difficulty score from 1 (easiest) to 10 (hardest)
- "reasoning": 1-sentence explanation

Example format:
[{{"number": 42, "difficulty": "easy", "llm_score": 2, "reasoning": "Only requires updating a config file."}}]

Return ONLY the JSON array, no other text."""

        response = self.generate(prompt, system=system, max_tokens=1000)

        # Parse JSON response
        try:
            # Extract JSON from response (handle markdown code blocks)
            import re
            json_match = re.search(r'\[.*\]', response, re.DOTALL)
            if json_match:
                rankings = json.loads(json_match.group())
                return rankings
        except (json.JSONDecodeError, AttributeError) as e:
            logger.warning(f"Failed to parse LLM ranking response: {e}")

        # Fallback: return neutral scores
        return [{"number": iss["number"], "difficulty": "medium", "llm_score": 5, "reasoning": "Unable to assess."} for iss in issues_summary]

    def generate_draft_pr(
        self,
        issue_title: str,
        issue_body: str,
        issue_number: int,
        relevant_files: list[dict],
        repo_name: str,
        fix_plan: str,
        file_contents: dict[str, str],
    ) -> dict:
        """Generate a complete draft PR skeleton."""
        if self.demo_mode:
            target_file = relevant_files[0]['path'] if relevant_files else "src/main.py"
            branch = f"fix/issue-{issue_number}"
            commit_msg = f"fix: resolve #{issue_number} - {issue_title[:50]}"
            pr_title = f"Fix #{issue_number}: {issue_title[:60]}"
            pr_desc = (
                f"## Summary\n"
                f"Resolves #{issue_number}. This PR implements the fix for `{issue_title}`.\n\n"
                f"## Changes\n"
                f"- Scoped adjustment in `{target_file}`\n"
                f"- Verified against test suite\n\n"
                f"## Checklist\n"
                f"- [x] Tests added/updated\n"
                f"- [x] Code conforms to project conventions\n"
                f"- [x] Documentation updated where appropriate"
            )
            code_stubs = (
                f"```diff\n"
                f"--- a/{target_file}\n"
                f"+++ b/{target_file}\n"
                f"@@ -15,4 +15,6 @@\n"
                f" # Fix for #{issue_number}\n"
                f"+# Targeted enhancement for {issue_title[:35]}\n"
                f"```"
            )
            return {
                "branch_name": branch,
                "commit_message": commit_msg,
                "pr_title": pr_title,
                "pr_description": pr_desc,
                "code_stubs": code_stubs,
                "raw_response": f"## BRANCH_NAME\n{branch}\n\n## COMMIT_MESSAGE\n{commit_msg}\n\n## PR_TITLE\n{pr_title}\n\n## PR_DESCRIPTION\n{pr_desc}\n\n## CODE_STUBS\n{code_stubs}",
            }

        files_ctx = "\n\n".join(
            f"### {f['path']}\n```\n{file_contents.get(f['path'], f['content'][:400])}\n```"
            for f in relevant_files[:3]
        )

        system = "You are a senior developer generating professional PR templates following Conventional Commits and GitHub best practices."
        prompt = f"""Repository: {repo_name}
Issue #{issue_number}: {issue_title}

Issue description:
{issue_body[:1000]}

Fix plan:
{fix_plan[:800]}

Relevant source files:
{files_ctx}

---
Generate a complete Draft PR skeleton with these sections (use the EXACT headers below):

## BRANCH_NAME
[suggest a branch name following git-flow: fix/issue-number-short-description]

## COMMIT_MESSAGE
[Conventional Commits format: type(scope): description
Body explaining what and why]

## PR_TITLE
[Concise, action-oriented title]

## PR_DESCRIPTION
[Full GitHub PR description with:
- Summary of changes
- Motivation/context (links to issue)
- Type of change checkboxes
- Testing instructions
- Screenshots placeholder if UI change]

## CODE_STUBS
[For each relevant file, provide starter code stubs/diffs showing:
- The specific function/section to modify
- A skeleton implementation with TODO comments
- Clearly marked as "starting point, not finished fix"

Format as diff blocks:
```diff
--- a/filename.py
+++ b/filename.py
@@ context @@
 existing line
+new line to add
-line to remove
```
]"""

        response = self.generate(prompt, system=system, max_tokens=2000)

        # Parse sections
        import re
        sections = {}
        section_pattern = r"## ([A-Z_]+)\n(.*?)(?=\n## [A-Z_]+|\Z)"
        for m in re.finditer(section_pattern, response, re.DOTALL):
            sections[m.group(1)] = m.group(2).strip()

        return {
            "branch_name": sections.get("BRANCH_NAME", f"fix/issue-{issue_number}"),
            "commit_message": sections.get("COMMIT_MESSAGE", f"fix: resolve #{issue_number} - {issue_title}"),
            "pr_title": sections.get("PR_TITLE", f"Fix #{issue_number}: {issue_title}"),
            "pr_description": sections.get("PR_DESCRIPTION", ""),
            "code_stubs": sections.get("CODE_STUBS", ""),
            "raw_response": response,
        }

    def answer_question(
        self,
        question: str,
        context_docs: list[dict],
        repo_name: str,
        chat_history: list[dict],
    ) -> Generator[str, None, None]:
        """RAG-based Q&A about the codebase. Streams the answer."""
        if self.demo_mode:
            context_files = ", ".join(f"`{d['path']}`" for d in context_docs[:3]) if context_docs else "the codebase"
            ans = (
                f"Based on the analysis of **{repo_name}** and matching files ({context_files}):\n\n"
                f"Regarding **'{question}'**:\n"
                f"The implementation is centered around {context_files}. "
                f"The module exports clear interfaces, with input validation performed before core processing logic is executed. "
                f"For new contributors, inspecting the corresponding unit tests provides the clearest illustration of the expected input/output contract."
            )
            for chunk in ans.split(" "):
                yield chunk + " "
            return

        context = "\n\n".join(
            f"**File: {doc['path']}**\n```\n{doc['content'][:600]}\n```"
            for doc in context_docs[:5]
        )
        history_str = "\n".join(
            f"{'User' if m['role'] == 'user' else 'Assistant'}: {m['content'][:200]}"
            for m in chat_history[-4:]  # Last 4 messages
        )

        system = (
            f"You are a helpful code assistant answering questions about the '{repo_name}' repository. "
            "Base your answers on the provided code context. Be specific and cite file names. "
            "If the context doesn't contain the answer, say so honestly."
        )
        prompt = f"""Recent conversation:
{history_str}

Relevant code context from the repository:
{context}

---
Question: {question}

Answer based on the code context above. Be specific, cite file names and function names where relevant."""

        yield from self.generate_stream(prompt, system=system, max_tokens=800)

    def compare_repos(self, repos_data: list[dict]) -> str:
        """Generate a comparison of multiple repos for beginner-friendliness."""
        if self.demo_mode:
            if not repos_data:
                return "No repositories provided for comparison."
            best = max(repos_data, key=lambda r: r.get("avg_readiness", 0))
            return (
                f"### ⚖️ Multi-Repository Comparison\n\n"
                f"**Top Recommendation:** **{best['name']}** (Average Readiness Score: {best.get('avg_readiness', 0):.0f}/100)\n\n"
                f"**Key Findings:**\n"
                f"- **{best['name']}** ranks highest in contributor readiness due to a favorable ratio of isolated starter issues and verifiable test suites.\n"
                f"- The codebase architecture demonstrates strong modularity, minimizing unintended ripple effects for first-time PRs.\n\n"
                f"**Decision Advice:**\n"
                f"Start with #{best['name']} by claiming an unassigned issue scoring above 70 on Contribution Readiness."
            )

        repos_summary = "\n\n".join(
            f"### {r['name']}\n"
            f"- Stars: {r.get('stars', 'N/A')}\n"
            f"- Languages: {', '.join(list(r.get('languages', {}).keys())[:3])}\n"
            f"- Avg readiness score: {r.get('avg_readiness', 'N/A')}\n"
            f"- Total beginner issues: {r.get('issue_count', 'N/A')}\n"
            f"- Architecture: {r.get('architecture_summary', '')[:300]}"
            for r in repos_data
        )

        system = "You are an expert helping developers choose their first open-source contribution."
        prompt = f"""Compare these repositories for beginner-friendliness for a first-time Hacktoberfest contributor:

{repos_summary}

Provide:
1. **Recommendation**: Which repo is best for beginners and why
2. **Per-repo analysis**: Strengths and weaknesses for newcomers
3. **Decision matrix**: Key factors (codebase complexity, community, issue quality, docs)
4. **Final verdict**: Clear recommendation with rationale

Be honest and specific."""

        return self.generate(prompt, system=system, max_tokens=1000)
