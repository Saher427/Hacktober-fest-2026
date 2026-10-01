"""
repo_analyzer.py — Cloning, tree-sitter parsing, and dependency graph construction.
"""
from __future__ import annotations

import ast
import hashlib
import logging
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

import git
import networkx as nx

logger = logging.getLogger(__name__)

# Extensions we can parse or at least summarize
PARSEABLE_EXTENSIONS = {".py", ".js", ".ts", ".jsx", ".tsx", ".java", ".go", ".rb", ".rs", ".cpp", ".c", ".h"}
TEXT_EXTENSIONS = {".md", ".txt", ".yaml", ".yml", ".json", ".toml", ".cfg", ".ini", ".env", ".sh"}
SKIP_DIRS = {
    ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
    "dist", "build", ".next", ".nuxt", "coverage", ".pytest_cache",
    "vendor", "third_party", "third-party", ".eggs", "*.egg-info",
    "site-packages", ".tox", "htmlcov", ".mypy_cache", ".ruff_cache",
}


@dataclass
class FileInfo:
    """Represents a parsed source file."""
    path: str                          # Relative path from repo root
    extension: str
    size_bytes: int
    functions: list[str] = field(default_factory=list)
    classes: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    docstring: str = ""
    summary: str = ""                  # LLM or heuristic summary
    line_count: int = 0
    complexity_score: int = 0         # Rough: num functions + classes + imports
    raw_content: str = ""             # Truncated snippet for LLM


@dataclass 
class RepoAnalysis:
    """Complete analysis result for a repository."""
    repo_url: str
    repo_name: str
    clone_path: str
    file_tree: list[str] = field(default_factory=list)
    files: dict[str, FileInfo] = field(default_factory=dict)
    dependency_graph: Optional[nx.DiGraph] = None
    architecture_summary: str = ""
    languages: dict[str, int] = field(default_factory=dict)
    total_files: int = 0
    total_lines: int = 0
    entry_points: list[str] = field(default_factory=list)


class RepoAnalyzer:
    """Handles cloning, parsing, and dependency graph construction."""

    def __init__(self, cache_dir: str = "./repos_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self._ts_available = self._check_tree_sitter()

    def _check_tree_sitter(self) -> bool:
        """Check if tree-sitter is usable."""
        try:
            import tree_sitter
            return True
        except ImportError:
            logger.warning("tree-sitter not available, falling back to AST/regex parsing.")
            return False

    def get_repo_hash(self, repo_url: str) -> str:
        """Get a stable cache key for a repo URL."""
        return hashlib.md5(repo_url.encode()).hexdigest()[:12]

    def get_clone_path(self, repo_url: str, repo_name: str) -> Path:
        """Get the local path where this repo would be cloned."""
        safe_name = re.sub(r"[^\w\-]", "_", repo_name)
        h = self.get_repo_hash(repo_url)
        return self.cache_dir / f"{safe_name}_{h}"

    def clone_or_pull(
        self,
        repo_url: str,
        repo_name: str,
        progress_callback=None,
    ) -> Path:
        """Clone a repo (or pull updates if already cloned). Returns local path."""
        clone_path = self.get_clone_path(repo_url, repo_name)

        if clone_path.exists():
            if progress_callback:
                progress_callback("Repo already cached — pulling latest changes...")
            try:
                repo = git.Repo(clone_path)
                origin = repo.remotes.origin
                origin.pull(depth=1)
                logger.info(f"Pulled updates to {clone_path}")
            except Exception as e:
                logger.warning(f"Pull failed ({e}), using existing clone.")
        else:
            if progress_callback:
                progress_callback(f"Cloning repository (shallow)...")
            try:
                git.Repo.clone_from(
                    repo_url,
                    clone_path,
                    depth=1,  # Shallow clone for speed
                    progress=None,
                )
                logger.info(f"Cloned {repo_url} → {clone_path}")
            except git.GitCommandError as e:
                raise RuntimeError(
                    f"Failed to clone repository: {e}\n\n"
                    "Make sure the repo URL is accessible. "
                    "For private repos, ensure your token has repo read permissions."
                )

        return clone_path

    def analyze(
        self,
        clone_path: Path,
        repo_url: str,
        repo_name: str,
        progress_callback=None,
        max_files: int = 200,
    ) -> RepoAnalysis:
        """Full analysis: walk files, parse, build dependency graph."""
        analysis = RepoAnalysis(
            repo_url=repo_url,
            repo_name=repo_name,
            clone_path=str(clone_path),
        )

        if progress_callback:
            progress_callback("Walking file tree...")

        all_files = self._walk_repo(clone_path, max_files=max_files)
        analysis.file_tree = [str(f.relative_to(clone_path)) for f in all_files]
        analysis.total_files = len(all_files)

        if progress_callback:
            progress_callback(f"Parsing {len(all_files)} source files...")

        lang_counts: dict[str, int] = {}
        for i, fpath in enumerate(all_files):
            rel = str(fpath.relative_to(clone_path))
            info = self._parse_file(fpath, rel)
            if info:
                analysis.files[rel] = info
                analysis.total_lines += info.line_count
                ext = info.extension.lstrip(".")
                lang_counts[ext] = lang_counts.get(ext, 0) + 1

            if progress_callback and i % 20 == 0:
                progress_callback(f"Parsing files... ({i+1}/{len(all_files)})")

        analysis.languages = lang_counts
        analysis.entry_points = self._detect_entry_points(analysis.files)

        if progress_callback:
            progress_callback("Building dependency graph...")

        analysis.dependency_graph = self._build_dependency_graph(analysis.files, clone_path)

        return analysis

    def _walk_repo(self, root: Path, max_files: int = 200) -> list[Path]:
        """Walk the repo and return relevant source files."""
        result = []
        skip_dirs_lower = {d.lower() for d in SKIP_DIRS}

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune skip dirs in-place
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in skip_dirs_lower and not d.startswith(".")
            ]

            for fname in filenames:
                fpath = Path(dirpath) / fname
                ext = fpath.suffix.lower()
                if ext in PARSEABLE_EXTENSIONS or ext in TEXT_EXTENSIONS:
                    # Skip very large files
                    try:
                        if fpath.stat().st_size > 500_000:
                            continue
                    except Exception:
                        continue
                    result.append(fpath)
                    if len(result) >= max_files:
                        return result

        return result

    def _parse_file(self, fpath: Path | str, rel_path: str) -> Optional[FileInfo]:
        """Parse a single file, extracting structure."""
        fpath = Path(fpath)
        try:
            content = fpath.read_text(encoding="utf-8", errors="replace")
        except Exception:
            return None

        ext = fpath.suffix.lower()
        lines = content.splitlines()
        info = FileInfo(
            path=rel_path,
            extension=ext,
            size_bytes=fpath.stat().st_size,
            line_count=len(lines),
            raw_content=content[:3000],  # First 3K chars for LLM context
        )

        if ext == ".py":
            self._parse_python(content, info)
        elif ext in {".js", ".ts", ".jsx", ".tsx"}:
            self._parse_js_ts(content, info)
        elif ext in {".java"}:
            self._parse_generic_oo(content, info, class_pat=r"class\s+(\w+)", func_pat=r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\(")
        elif ext in {".go"}:
            self._parse_generic_oo(content, info, class_pat=r"type\s+(\w+)\s+struct", func_pat=r"func\s+(?:\(\w+\s+\*?\w+\)\s+)?(\w+)\s*\(")
        elif ext in {".rb"}:
            self._parse_generic_oo(content, info, class_pat=r"class\s+(\w+)", func_pat=r"def\s+(\w+)")
        elif ext in {".rs"}:
            self._parse_generic_oo(content, info, class_pat=r"struct\s+(\w+)|impl\s+(\w+)", func_pat=r"fn\s+(\w+)\s*\(")
        else:
            # For text files, extract first meaningful content as docstring
            info.docstring = "\n".join(lines[:10])

        info.complexity_score = len(info.functions) + len(info.classes) * 2 + len(info.imports)
        return info

    def _parse_python(self, content: str, info: FileInfo):
        """Parse Python with stdlib ast for accuracy."""
        try:
            tree = ast.parse(content)
            for node in ast.walk(tree):
                if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    info.functions.append(node.name)
                    if (not info.docstring and ast.get_docstring(node) and
                            node.col_offset == 0):
                        pass  # top-level docstring handled below
                elif isinstance(node, ast.ClassDef):
                    info.classes.append(node.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        info.imports.append(alias.name)
                elif isinstance(node, ast.ImportFrom):
                    mod = node.module or ""
                    info.imports.append(mod)

            # Module docstring
            if isinstance(tree.body[0] if tree.body else None, ast.Expr):
                ds = ast.get_docstring(tree)
                if ds:
                    info.docstring = ds[:500]
        except SyntaxError:
            # Fall back to regex
            self._parse_python_regex(content, info)

    def _parse_python_regex(self, content: str, info: FileInfo):
        """Fallback regex-based Python parsing."""
        info.functions = re.findall(r"^def\s+(\w+)\s*\(", content, re.MULTILINE)
        info.classes = re.findall(r"^class\s+(\w+)", content, re.MULTILINE)
        imports = re.findall(r"^(?:import|from)\s+([\w.]+)", content, re.MULTILINE)
        info.imports = imports

    def _parse_js_ts(self, content: str, info: FileInfo):
        """Parse JS/TS with regex (tree-sitter optional enhancement)."""
        # Functions (various forms)
        func_patterns = [
            r"function\s+(\w+)\s*\(",
            r"(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:function|\([^)]*\)\s*=>|\w+\s*=>)",
            r"(?:async\s+)?(\w+)\s*\([^)]*\)\s*\{",
            r"(\w+)\s*:\s*(?:async\s+)?function",
        ]
        seen = set()
        for pat in func_patterns:
            for m in re.finditer(pat, content):
                name = m.group(1)
                if name not in seen and not name[0].isupper():
                    info.functions.append(name)
                    seen.add(name)

        # Classes
        info.classes = re.findall(r"class\s+(\w+)", content)

        # Imports
        import_patterns = [
            r"import\s+.*?from\s+['\"]([^'\"]+)['\"]",
            r"require\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
            r"import\s*\(\s*['\"]([^'\"]+)['\"]\s*\)",
        ]
        seen_imports = set()
        for pat in import_patterns:
            for m in re.finditer(pat, content):
                src = m.group(1)
                if src not in seen_imports:
                    info.imports.append(src)
                    seen_imports.add(src)

        # Docstring / JSDoc
        jsdoc = re.search(r"/\*\*(.*?)\*/", content, re.DOTALL)
        if jsdoc:
            info.docstring = jsdoc.group(1).strip()[:500]

    def _parse_generic_oo(
        self, content: str, info: FileInfo,
        class_pat: str, func_pat: str
    ):
        """Generic OO-style parsing with customizable patterns."""
        for m in re.finditer(class_pat, content):
            # Handle groups with alternation
            name = next((g for g in m.groups() if g), None)
            if name:
                info.classes.append(name)

        for m in re.finditer(func_pat, content):
            name = next((g for g in m.groups() if g), None)
            if name:
                info.functions.append(name)

        # Generic import-like lines
        imports = re.findall(r"^(?:import|use|require|#include|from)\s+([\w./\"<>]+)", content, re.MULTILINE)
        info.imports = [i.strip('"<>') for i in imports]

    def _detect_entry_points(self, files: dict[str, FileInfo]) -> list[str]:
        """Heuristically detect entry points (main files, index files, app files)."""
        entry_candidates = []
        entry_names = {"main", "app", "index", "server", "cli", "run", "start", "__main__"}
        for path in files:
            stem = Path(path).stem.lower()
            if stem in entry_names:
                entry_candidates.append(path)
        return entry_candidates[:5]

    def _build_dependency_graph(
        self, files: dict[str, FileInfo], root: Path
    ) -> nx.DiGraph:
        """Build a file-level dependency graph from import statements."""
        G = nx.DiGraph()

        # Add all files as nodes
        for path, info in files.items():
            G.add_node(
                path,
                functions=info.functions,
                classes=info.classes,
                complexity=info.complexity_score,
                lines=info.line_count,
                extension=info.extension,
            )

        # Resolve imports to actual files
        file_paths = set(files.keys())
        path_stems = {
            Path(p).stem: p for p in file_paths
        }  # stem → actual path

        for path, info in files.items():
            for imp in info.imports:
                # Normalize import to a potential file path
                resolved = self._resolve_import(imp, path, file_paths, path_stems, root)
                if resolved and resolved != path:
                    G.add_edge(path, resolved, weight=1)

        return G

    def _resolve_import(
        self,
        import_str: str,
        importer_path: str,
        all_paths: set[str],
        path_stems: dict[str, str],
        root: Path,
    ) -> Optional[str]:
        """Try to resolve an import string to a local file path."""
        # Skip stdlib and third-party by checking for dots at start
        if import_str.startswith(("http", "https", "@", "~")):
            return None

        # Convert dots to path separators (Python-style)
        candidate = import_str.replace(".", "/")

        # Potential file extensions
        for ext in [".py", ".js", ".ts", ".jsx", ".tsx"]:
            for prefix in ["", "src/", "lib/", "app/"]:
                full = f"{prefix}{candidate}{ext}"
                if full in all_paths:
                    return full
                # Also try just the stem
                stem = import_str.split(".")[-1].split("/")[-1]
                if stem in path_stems:
                    return path_stems[stem]

        # JS relative imports (./foo or ../bar)
        if import_str.startswith(("./", "../")):
            importer_dir = str(Path(importer_path).parent)
            normalized = import_str.lstrip("./").lstrip("../")
            stem = normalized.split("/")[-1]
            if stem in path_stems:
                return path_stems[stem]

        return None

    def get_file_content(self, clone_path: str, rel_path: str) -> str:
        """Read file content from clone."""
        try:
            return (Path(clone_path) / rel_path).read_text(encoding="utf-8", errors="replace")
        except Exception:
            return ""

    def compute_file_recency(self, clone_path: str, rel_path: str) -> int:
        """Count commits to a file in the past 90 days using git log."""
        try:
            result = subprocess.run(
                ["git", "log", "--oneline", "--follow",
                 f"--since=90 days ago", "--", rel_path],
                cwd=clone_path,
                capture_output=True,
                text=True,
                timeout=10,
            )
            lines = [l for l in result.stdout.strip().splitlines() if l]
            return len(lines)
        except Exception:
            return 0

    def check_has_tests(self, files: dict[str, FileInfo], rel_path: str) -> bool:
        """Check if a test file exists for the given file."""
        stem = Path(rel_path).stem.lower()
        for path in files:
            path_lower = path.lower()
            if ("test" in path_lower or "spec" in path_lower) and stem in path_lower:
                return True
        return False
