"""
app.py — First Issue Finder: Streamlit UI and orchestration.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Optional

import streamlit as st
import networkx as nx
from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
#  Page Config (must be first Streamlit call)
# ─────────────────────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="First Issue Finder · Hacktoberfest",
    page_icon="🎃",
    layout="wide",
    initial_sidebar_state="expanded",
)

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
#  Lazy imports (avoid crashing if a dep is missing)
# ─────────────────────────────────────────────────────────────────────────────
def _import_or_warn(module, name):
    try:
        return __import__(module)
    except ImportError:
        st.warning(f"⚠️ Optional dependency '{name}' not installed. Some features disabled.")
        return None


# ─────────────────────────────────────────────────────────────────────────────
#  CSS — Premium dark glassmorphism design
# ─────────────────────────────────────────────────────────────────────────────
CUSTOM_CSS = """
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap');

:root {
    --bg-canvas: #0d1117;
    --bg-surface: #161b22;
    --bg-surface-hover: #1c2128;
    --border-default: #30363d;
    --border-subtle: #21262d;
    --fg-default: #f0f6fc;
    --fg-muted: #8b949e;
    --fg-subtle: #6e7681;
    --accent: #2f81f7;
    --accent-hover: #388bfd;
    --success: #238636;
    --success-border: #2ea043;
    --warning: #d29922;
    --danger: #f85149;
    --font-sans: 'Inter', -apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif;
    --font-mono: 'JetBrains Mono', ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace;
}

/* Global resets & typography */
html, body, [class*="css"] {
    font-family: var(--font-sans);
    color: var(--fg-default);
    background-color: var(--bg-canvas) !important;
}

.stApp {
    background-color: var(--bg-canvas) !important;
}

.block-container {
    padding: 1.75rem 2.25rem 4rem;
    max-width: 1360px;
}

/* Header */
.hero-header {
    border-bottom: 1px solid var(--border-default);
    padding: 0.5rem 0 1.5rem 0;
    margin-bottom: 1.5rem;
    text-align: left;
}
.hero-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    background: #21262d;
    border: 1px solid var(--border-default);
    border-radius: 4px;
    padding: 0.2rem 0.6rem;
    font-size: 0.72rem;
    font-weight: 600;
    color: #58a6ff;
    font-family: var(--font-mono);
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.75rem;
}
.hero-title {
    font-size: 2rem;
    font-weight: 700;
    color: var(--fg-default);
    letter-spacing: -0.02em;
    margin: 0 0 0.5rem 0;
    line-height: 1.2;
}
.hero-sub {
    font-size: 0.95rem;
    color: var(--fg-muted);
    max-width: 820px;
    margin: 0;
    line-height: 1.5;
}

/* Developer cards */
.glass-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: 1.25rem;
    margin-bottom: 1rem;
}
.glass-card:hover {
    border-color: #8b949e;
}

/* Issue cards */
.issue-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: 1.25rem;
    margin-bottom: 0.75rem;
    border-left: 3px solid var(--border-default);
    transition: border-color 0.15s ease, background 0.15s ease;
}
.issue-card:hover {
    background: var(--bg-surface-hover);
    border-color: #8b949e;
}
.issue-card.difficulty-great { border-left-color: var(--success); }
.issue-card.difficulty-good { border-left-color: var(--warning); }
.issue-card.difficulty-moderate { border-left-color: #f0883e; }
.issue-card.difficulty-advanced { border-left-color: var(--danger); }

/* Score indicators */
.score-badge {
    display: inline-flex;
    align-items: center;
    gap: 0.4rem;
    padding: 0.25rem 0.65rem;
    border-radius: 4px;
    font-size: 0.8rem;
    font-weight: 600;
    font-family: var(--font-mono);
    border: 1px solid;
}
.score-ring {
    width: 48px;
    height: 48px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    justify-content: center;
    font-weight: 700;
    font-size: 1.1rem;
    border: 1px solid;
    font-family: var(--font-mono);
    background: rgba(255,255,255,0.03);
}

/* Factor breakdown */
.factor-row {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    margin-bottom: 0.4rem;
}
.factor-label {
    min-width: 105px;
    font-size: 0.75rem;
    font-weight: 600;
    color: var(--fg-muted);
    font-family: var(--font-mono);
    text-transform: uppercase;
}
.factor-bar-bg {
    flex: 1;
    height: 6px;
    background: #21262d;
    border-radius: 3px;
    overflow: hidden;
}
.factor-bar-fill {
    height: 100%;
    border-radius: 3px;
}
.factor-value {
    min-width: 32px;
    text-align: right;
    font-size: 0.78rem;
    font-weight: 600;
    color: var(--fg-default);
    font-family: var(--font-mono);
}
.factor-desc {
    font-size: 0.73rem;
    color: var(--fg-subtle);
    margin: -0.1rem 0 0.5rem 0;
}

/* Chips & tags */
.label-chip {
    display: inline-block;
    padding: 0.15rem 0.5rem;
    border-radius: 4px;
    font-size: 0.72rem;
    font-family: var(--font-mono);
    font-weight: 500;
    border: 1px solid var(--border-default);
    background: #21262d;
    color: var(--fg-muted);
    margin: 0.1rem;
}
.label-beginner {
    color: #3fb950;
    border-color: rgba(46,160,67,0.4);
    background: rgba(46,160,67,0.12);
}
.label-default {
    color: var(--fg-muted);
    border-color: var(--border-default);
    background: #161b22;
}

/* Step plans & code blocks */
.step-plan {
    background: #0d1117;
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: 1.1rem 1.3rem;
    font-size: 0.88rem;
    line-height: 1.6;
}
.pr-block {
    font-family: var(--font-mono);
    background: #0d1117;
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: 1rem;
    font-size: 0.82rem;
    white-space: pre-wrap;
    word-break: break-word;
    color: #c9d1d9;
}

/* Chat */
.chat-msg-user {
    background: #1c2128;
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    font-size: 0.88rem;
}
.chat-msg-ai {
    background: #161b22;
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: 0.75rem 1rem;
    margin: 0.5rem 0;
    font-size: 0.88rem;
    line-height: 1.6;
}

/* Section Header */
.section-header {
    display: flex;
    align-items: center;
    gap: 0.6rem;
    margin: 1.75rem 0 1rem;
    padding-bottom: 0.5rem;
    border-bottom: 1px solid var(--border-default);
}
.section-header h2 {
    font-size: 1.2rem;
    font-weight: 600;
    margin: 0;
    color: var(--fg-default);
}

/* Metric Mini */
.metric-mini {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: 0.85rem 1rem;
    text-align: left;
}
.metric-mini .label {
    font-size: 0.72rem;
    color: var(--fg-muted);
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.05em;
    margin-bottom: 0.25rem;
}
.metric-mini .value {
    font-size: 1.5rem;
    font-weight: 700;
    color: var(--fg-default);
    font-family: var(--font-mono);
}

/* Info banner */
.info-banner {
    background: #161b22;
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: 0.65rem 1rem;
    font-size: 0.82rem;
    color: var(--fg-muted);
    margin: 0.5rem 0 1rem;
}

/* Comparison cards */
.compare-card {
    background: var(--bg-surface);
    border: 1px solid var(--border-default);
    border-radius: 6px;
    padding: 1.25rem;
    text-align: left;
}
.compare-card.winner {
    border-color: var(--success);
}
.compare-card .repo-name {
    font-size: 1rem;
    font-weight: 700;
    margin-bottom: 0.5rem;
    color: var(--fg-default);
}
.compare-card .big-score {
    font-size: 2.2rem;
    font-weight: 800;
    line-height: 1;
    font-family: var(--font-mono);
}

/* Streamlit component overrides */
.stTextInput > div > div > input,
.stTextArea > div > div > textarea {
    background: #0d1117 !important;
    border: 1px solid var(--border-default) !important;
    border-radius: 6px !important;
    color: var(--fg-default) !important;
    font-family: var(--font-sans) !important;
}
.stTextInput > div > div > input:focus,
.stTextArea > div > div > textarea:focus {
    border-color: #58a6ff !important;
    box-shadow: 0 0 0 1px #58a6ff !important;
}

.stButton > button {
    background: #21262d !important;
    color: #f0f6fc !important;
    border: 1px solid var(--border-default) !important;
    border-radius: 6px !important;
    font-weight: 500 !important;
    font-size: 0.85rem !important;
    letter-spacing: 0 !important;
    transition: background 0.12s ease !important;
}
.stButton > button:hover {
    background: #30363d !important;
    border-color: #8b949e !important;
}
button[kind="primary"] {
    background: #238636 !important;
    border-color: #2ea043 !important;
    color: #ffffff !important;
}
button[kind="primary"]:hover {
    background: #2ea043 !important;
}

section[data-testid="stSidebar"] {
    background: #0d1117 !important;
    border-right: 1px solid var(--border-default) !important;
}

.stExpander {
    background: var(--bg-surface) !important;
    border: 1px solid var(--border-default) !important;
    border-radius: 6px !important;
}

/* Scrollbar */
::-webkit-scrollbar { width: 6px; height: 6px; }
::-webkit-scrollbar-track { background: transparent; }
::-webkit-scrollbar-thumb { background: #30363d; border-radius: 3px; }
::-webkit-scrollbar-thumb:hover { background: #58a6ff; }
</style>
"""

st.markdown(CUSTOM_CSS, unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Session State Init
# ─────────────────────────────────────────────────────────────────────────────
def init_session():
    defaults = {
        "analysis_done": False,
        "repo_analysis": None,
        "analyzed_issues": [],
        "raw_issues": [],
        "gh_repo": None,
        "chat_history": [],
        "current_repo_url": "",
        "multi_repo_results": [],
        "selected_pr_issue": None,
        "generated_prs": {},
        "error": None,
        "step_status": {},
        # Multi-repo
        "multi_done": False,
        "multi_analyses": [],
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_session()


# ─────────────────────────────────────────────────────────────────────────────
#  Helper: get settings from sidebar (cached in session)
# ─────────────────────────────────────────────────────────────────────────────
def get_settings():
    return {
        "github_token": st.session_state.get("_github_token", os.getenv("GITHUB_TOKEN", "")),
        "ollama_url": st.session_state.get("_ollama_url", os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")),
        "model": st.session_state.get("_model", os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")),
        "embed_model": st.session_state.get("_embed_model", os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text")),
        "repos_cache": os.getenv("REPOS_CACHE_DIR", "./repos_cache"),
        "chroma_dir": os.getenv("CHROMA_PERSIST_DIR", "./chroma_db"),
        "demo_mode": st.session_state.get("_demo_mode", False),
    }


def get_llm_client(settings: dict | None = None):
    from llm import OllamaClient
    if settings is None:
        settings = get_settings()
    return OllamaClient(
        base_url=settings["ollama_url"],
        model=settings["model"],
        demo_mode=settings.get("demo_mode", False),
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────────────────────────────────────
with st.sidebar:
    st.markdown("## ⚙️ Configuration")
    st.markdown("---")

    st.markdown("### 🔑 GitHub Token")
    token_val = st.text_input(
        "Personal Access Token",
        value=os.getenv("GITHUB_TOKEN", ""),
        type="password",
        key="_github_token",
        help="Required for higher rate limits and private repos. Create at github.com/settings/tokens",
        placeholder="ghp_...",
    )
    if not token_val:
        st.markdown('<div class="info-banner">⚠️ No token — limited to 60 req/hr</div>', unsafe_allow_html=True)

    st.markdown("### 🤖 Ollama Settings")
    st.text_input(
        "Ollama URL",
        value=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
        key="_ollama_url",
        help="Default: http://localhost:11434",
    )

    # Check Ollama status
    from github_client import GitHubClient as _GHC
    _settings = get_settings()
    _gh_tmp = _GHC()
    _ollama_ok, _models = _gh_tmp.validate_ollama(_settings["ollama_url"])

    if _ollama_ok:
        st.markdown('<div style="color:#22c55e;font-size:0.82rem;margin-bottom:0.5rem;">✅ Ollama connected</div>', unsafe_allow_html=True)
        model_choices = _models if _models else ["qwen2.5-coder:3b", "qwen2.5-coder:7b"]
        default_model = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b")
        try:
            default_idx = model_choices.index(default_model)
        except ValueError:
            default_idx = 0
        st.selectbox("Model", model_choices, index=default_idx, key="_model")
        st.session_state["_demo_mode"] = False
    else:
        st.markdown('<div style="color:#f59e0b;font-size:0.82rem;margin-bottom:0.5rem;">⚡ Ollama offline (localhost:11434)</div>', unsafe_allow_html=True)
        st.checkbox(
            "Enable Heuristic Demo Mode",
            value=True,
            key="_demo_mode",
            help="Run complete pipeline with AST parsing, dependency graph, and readiness scoring without requiring Ollama running."
        )
        st.text_input("Model", value=os.getenv("OLLAMA_MODEL", "qwen2.5-coder:3b"), key="_model")

    st.text_input("Embed Model", value=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"), key="_embed_model")

    st.markdown("---")
    st.markdown("### 🔒 Privacy")
    st.markdown(
        '<div style="font-size:0.78rem;color:#64748b;line-height:1.6;">'
        "All analysis runs <b>100% locally</b> on your machine.<br>"
        "No data is sent to external servers.<br>"
        "Repos are cached at <code>./repos_cache/</code>"
        "</div>",
        unsafe_allow_html=True,
    )

    st.markdown("---")
    st.markdown("### 🎃 About")
    st.markdown(
        '<div style="font-size:0.78rem;color:#64748b;line-height:1.6;">'
        "Built for <b>Hacktoberfest 2024</b>.<br>"
        "Powered by <b>Qwen2.5-Coder</b> via Ollama.<br>"
        "<a href='https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct' style='color:#f97316;'>Model License →</a>"
        "</div>",
        unsafe_allow_html=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Hero Header
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("""
<div class="hero-header">
    <div class="hero-badge">First Issue Finder · Contributor Onboarding</div>
    <div class="hero-title">Open-Source Codebase Navigator & Issue Matcher</div>
    <div class="hero-sub">
        Explore repository architecture, inspect dependency graphs, and rank beginner-friendly issues by verified contribution readiness — runs completely locally on your system.
    </div>
</div>
""", unsafe_allow_html=True)


# ─────────────────────────────────────────────────────────────────────────────
#  Rendering Helper Functions (defined before tabs to avoid NameError)
# ─────────────────────────────────────────────────────────────────────────────

def _render_dependency_graph(repo_analysis, analyzed_issues):
    """Render interactive dependency graph using pyvis."""
    G = repo_analysis.dependency_graph
    if G is None or len(G.nodes) == 0:
        st.info("No dependency graph available (no parseable imports found).")
        return

    # Build file → issues mapping
    file_to_issues = {}
    for issue in (analyzed_issues or []):
        for f in issue.relevant_files:
            path = f["path"]
            if path not in file_to_issues:
                file_to_issues[path] = []
            file_to_issues[path].append(f"#{issue.number}")

    try:
        from pyvis.network import Network
        import tempfile as _tempfile

        # Color nodes by extension
        ext_colors = {
            ".py": "#3b82f6",
            ".js": "#f59e0b",
            ".ts": "#2563eb",
            ".tsx": "#06b6d4",
            ".jsx": "#a78bfa",
            ".go": "#22c55e",
            ".rb": "#ef4444",
            ".rs": "#f97316",
            ".java": "#a855f7",
        }

        net = Network(
            height="440px",
            width="100%",
            bgcolor="#0a0e1a",
            font_color="#94a3b8",
            directed=True,
        )
        net.barnes_hut(spring_length=120, spring_strength=0.04, damping=0.09)

        # Limit to top N nodes by complexity for visual clarity
        top_nodes = sorted(
            G.nodes(data=True),
            key=lambda x: x[1].get("complexity", 0),
            reverse=True,
        )[:50]
        top_node_ids = {n[0] for n in top_nodes}

        for node_id, data in top_nodes:
            ext = data.get("extension", ".txt")
            color = ext_colors.get(ext, "#64748b")
            complexity = data.get("complexity", 1)
            size = max(10, min(40, 8 + complexity * 1.5))
            issues_here = file_to_issues.get(node_id, [])
            border_color = "#f97316" if issues_here else color
            border_width = 3 if issues_here else 1
            short_name = node_id.split("/")[-1]
            title = f"<b>{node_id}</b><br>Complexity: {complexity}<br>Lines: {data.get('lines',0)}"
            if issues_here:
                title += f"<br>Issues: {', '.join(issues_here)}"
            net.add_node(
                node_id,
                label=short_name,
                title=title,
                size=size,
                color={"background": color, "border": border_color},
                borderWidth=border_width,
                font={"size": 10, "face": "Inter"},
            )

        for src, dst in G.edges():
            if src in top_node_ids and dst in top_node_ids:
                net.add_edge(src, dst, color="rgba(148,163,184,0.3)", width=1.5)

        net.set_options("""
        {
          "interaction": {"hover": true, "tooltipDelay": 100},
          "physics": {"stabilization": {"iterations": 100}},
          "edges": {"arrows": {"to": {"enabled": true, "scaleFactor": 0.6}}, "smooth": {"type": "dynamic"}}
        }""")

        tmp = _tempfile.NamedTemporaryFile(suffix=".html", delete=False, mode="w")
        net.save_graph(tmp.name)
        tmp.close()
        with open(tmp.name, "r") as f:
            html_content = f.read()
        os.unlink(tmp.name)

        html_content = html_content.replace(
            "<body>", '<body style="background:#0a0e1a;margin:0;padding:0;">'
        )
        st.components.v1.html(html_content, height=450, scrolling=False)

        ext_legend = [
            (".py", "#3b82f6", "Python"), (".js", "#f59e0b", "JavaScript"),
            (".ts", "#2563eb", "TypeScript"), (".go", "#22c55e", "Go"),
        ]
        legend_html = '<div style="display:flex;gap:1rem;flex-wrap:wrap;margin-top:0.5rem;">'
        for ext, color, name in ext_legend:
            if any(n[1].get("extension") == ext for n in top_nodes):
                legend_html += f'<span style="font-size:0.72rem;color:{color};">■ {name}</span>'
        legend_html += '<span style="font-size:0.72rem;color:#f97316;">■ Has open issues</span>'
        legend_html += "</div>"
        st.markdown(legend_html, unsafe_allow_html=True)

    except ImportError:
        st.info("Install `pyvis` for interactive graph: `pip install pyvis`")
        st.markdown(f"**{len(G.nodes())} nodes**, **{len(G.edges())} edges** in dependency graph")
        if G.nodes():
            top = sorted(G.degree(), key=lambda x: x[1], reverse=True)[:10]
            for node, deg in top:
                st.markdown(f"- `{node}` — {deg} connections")
    except Exception as e:
        st.warning(f"Graph rendering error: {e}")


def _render_score_bar(label: str, score: float, description: str, color: str = "#f97316"):
    """Render a factor bar for the readiness score breakdown."""
    st.markdown(
        f"""<div class="factor-row">
  <div class="factor-label">{label}</div>
  <div class="factor-bar-bg"><div class="factor-bar-fill" style="width:{score}%;background:{color};"></div></div>
  <div class="factor-value">{score:.0f}</div>
</div>
<div class="factor-desc">{description}</div>""",
        unsafe_allow_html=True,
    )


def _render_issues(analyzed_issues, repo_analysis, raw_issues):
    """Render all issue cards with expandable details."""
    from readiness_score import get_score_color, get_score_label
    from issue_matcher import IssueMatcher
    from embeddings import EmbeddingStore
    from github_client import GitHubClient
    from llm import OllamaClient
    from repo_analyzer import RepoAnalyzer

    settings = get_settings()
    raw_issue_map = {iss["number"]: iss for iss in raw_issues}

    for idx, issue in enumerate(analyzed_issues):
        readiness = issue.readiness
        score = readiness.total_score if readiness else 0
        color = get_score_color(score)
        label = get_score_label(score)

        chips_html = ""
        for lbl in issue.labels[:5]:
            is_beginner = any(b in lbl.lower() for b in ["good first", "beginner", "easy", "help wanted"])
            chip_class = "label-beginner" if is_beginner else "label-default"
            chips_html += f'<span class="label-chip {chip_class}">{lbl}</span>'

        header = (
            f"**#{issue.number}** · {issue.title[:80]}"
            f"{'...' if len(issue.title) > 80 else ''}"
        )

        with st.expander(header, expanded=(idx == 0)):
            col_score, col_details = st.columns([1, 4], gap="large")

            with col_score:
                st.markdown(
                    f'<div style="text-align:center;padding:1rem 0;">'
                    f'<div class="score-ring" style="color:{color};border-color:{color};margin:0 auto 0.75rem;">{score:.0f}</div>'
                    f'<div style="font-size:0.9rem;font-weight:700;color:{color};">{label}</div>'
                    f'<div style="font-size:0.75rem;color:#64748b;margin-top:0.25rem;">{issue.difficulty_label}</div>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                st.markdown(
                    f'<div style="font-size:0.78rem;color:#64748b;line-height:2;">'
                    f'📅 {issue.age_days}d old<br>'
                    f'💬 {issue.comment_count} comments<br>'
                    f'{"🔒 Assigned" if issue.is_assigned else "🔓 Unassigned"}<br>'
                    f'</div>',
                    unsafe_allow_html=True,
                )
                if chips_html:
                    st.markdown(chips_html, unsafe_allow_html=True)
                st.markdown(f"[View on GitHub →]({issue.url})")

            with col_details:
                sub_tab1, sub_tab2, sub_tab3, sub_tab4 = st.tabs([
                    "📊 Readiness Score",
                    "💡 Explanation",
                    "🛠️ Fix Plan",
                    "📁 Relevant Files",
                ])

                with sub_tab1:
                    st.markdown("**Contribution Readiness Score Breakdown**")
                    st.markdown(
                        '<div style="font-size:0.75rem;color:#64748b;margin-bottom:0.75rem;">'
                        "Each factor contributes to the total score with transparent weights. "
                        "Higher = more beginner-friendly.</div>",
                        unsafe_allow_html=True,
                    )
                    if readiness:
                        _render_score_bar("Scope (30%)", readiness.scope_score, readiness.scope_label, "#3b82f6")
                        _render_score_bar("Tests (20%)", readiness.test_score, readiness.test_label, "#22c55e")
                        _render_score_bar("Stability (20%)", readiness.stability_score, readiness.stability_label, "#f59e0b")
                        _render_score_bar("Freshness (20%)", readiness.freshness_score, readiness.freshness_label, "#a855f7")
                        _render_score_bar("Clarity (10%)", readiness.clarity_score, readiness.clarity_label, "#06b6d4")
                        st.markdown("---")
                        st.markdown(
                            f'<div style="display:flex;align-items:center;gap:0.75rem;">'
                            f'<div class="score-ring" style="color:{color};border-color:{color};width:42px;height:42px;font-size:0.9rem;">{score:.0f}</div>'
                            f'<div><div style="font-weight:700;font-size:1rem;">Total Readiness Score</div>'
                            f'<div style="color:#64748b;font-size:0.8rem;">LLM assessment: {issue.llm_difficulty} (score: {issue.llm_score}/10)</div></div>'
                            f'</div>',
                            unsafe_allow_html=True,
                        )

                with sub_tab2:
                    if issue.explanation:
                        st.markdown(issue.explanation)
                    else:
                        raw = raw_issue_map.get(issue.number, {})
                        if st.button(f"Generate Explanation", key=f"explain_{issue.number}"):
                            with st.spinner("Analyzing issue with LLM..."):
                                try:
                                    llm_client = get_llm_client(settings)
                                    issue.explanation = llm_client.explain_issue(
                                        issue_title=issue.title,
                                        issue_body=issue.body,
                                        issue_comments=raw.get("comment_texts", []),
                                        relevant_files=issue.relevant_files,
                                        repo_name=repo_analysis.repo_name,
                                    )
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"LLM error: {e}")

                with sub_tab3:
                    if issue.fix_plan:
                        st.markdown(issue.fix_plan)
                    else:
                        if st.button(f"Generate Fix Plan", key=f"plan_{issue.number}"):
                            with st.spinner("Generating step-by-step plan..."):
                                try:
                                    llm_client = get_llm_client(settings)
                                    issue.fix_plan = llm_client.generate_fix_plan(
                                        issue_title=issue.title,
                                        issue_body=issue.body,
                                        relevant_files=issue.relevant_files,
                                        repo_name=repo_analysis.repo_name,
                                        architecture_context=repo_analysis.architecture_summary[:500],
                                    )
                                    st.rerun()
                                except Exception as e:
                                    st.error(f"LLM error: {e}")

                with sub_tab4:
                    if issue.relevant_files:
                        st.markdown(f"**{len(issue.relevant_files)} most relevant files** (found via semantic search):")
                        for rf in issue.relevant_files:
                            path = rf["path"]
                            meta = rf.get("metadata", {})
                            dist = rf.get("distance", 0)
                            relevance = max(0, 100 - int(dist * 100)) if dist else 80
                            st.markdown(
                                f'<div class="factor-row">'
                                f'<code style="flex:1;font-size:0.8rem;">{path}</code>'
                                f'<div class="factor-bar-bg" style="max-width:100px;"><div class="factor-bar-fill" style="width:{relevance}%;background:#f97316;"></div></div>'
                                f'<div class="factor-value">{relevance}%</div>'
                                f'</div>',
                                unsafe_allow_html=True,
                            )
                            funcs = meta.get("functions", "")
                            classes = meta.get("classes", "")
                            if funcs or classes:
                                st.markdown(
                                    f'<div style="font-size:0.72rem;color:#64748b;margin-bottom:0.5rem;padding-left:0.5rem;">'
                                    f'{"Functions: " + funcs[:80] if funcs else ""}'
                                    f'{" · Classes: " + classes[:60] if classes else ""}'
                                    f'</div>',
                                    unsafe_allow_html=True,
                                )
                    else:
                        st.info("No relevant files identified (embedding search returned no results).")

            st.markdown("---")
            pr_col1, pr_col2 = st.columns([1, 4])
            with pr_col1:
                if st.button(
                    "📝 Generate Draft PR",
                    key=f"pr_btn_{issue.number}",
                    use_container_width=True,
                ):
                    with st.spinner("Generating draft PR skeleton..."):
                        try:
                            from repo_analyzer import RepoAnalyzer as RA
                            ra = RA(settings["repos_cache"])
                            llm_client = get_llm_client(settings)
                            _embed = EmbeddingStore(
                                persist_dir=settings["chroma_dir"],
                                ollama_base_url=settings["ollama_url"],
                                embed_model=settings["embed_model"],
                            )
                            from github_client import GitHubClient as GHC
                            _matcher = IssueMatcher(GHC(settings["github_token"]), ra, _embed, llm_client)
                            pr = _matcher.generate_draft_pr(issue, repo_analysis)
                            st.session_state.generated_prs[issue.number] = pr
                            st.rerun()
                        except Exception as e:
                            st.error(f"Draft PR generation failed: {e}")

            pr_data = st.session_state.generated_prs.get(issue.number)
            if pr_data:
                _render_draft_pr(pr_data, issue.number)


def _render_draft_pr(pr_data: dict, issue_num: int):
    """Render the draft PR card."""
    st.markdown("### 📝 Draft PR Skeleton")
    st.markdown(
        '<div class="info-banner">⚠️ This is a starting point, not a finished fix. '
        "Review and adapt before submitting.</div>",
        unsafe_allow_html=True,
    )
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🌿 Branch Name**")
        st.code(pr_data.get("branch_name", f"fix/issue-{issue_num}"), language="bash")
    with col2:
        st.markdown("**💬 Commit Message**")
        st.code(pr_data.get("commit_message", ""), language="text")
    st.markdown("**📄 PR Title**")
    st.code(pr_data.get("pr_title", ""), language="text")
    st.markdown("**📋 PR Description**")
    st.markdown(
        f'<div class="pr-block">{pr_data.get("pr_description", "")}</div>',
        unsafe_allow_html=True,
    )
    if pr_data.get("code_stubs"):
        st.markdown("**🔧 Code Stubs / Diff**")
        stubs = pr_data["code_stubs"]
        diff_blocks = re.findall(r"```diff(.*?)```", stubs, re.DOTALL)
        if diff_blocks:
            for block in diff_blocks:
                st.code(block.strip(), language="diff")
        else:
            st.markdown(f'<div class="pr-block">{stubs}</div>', unsafe_allow_html=True)
    full_pr = (
        f"Branch: {pr_data.get('branch_name', '')}\n\n"
        f"Commit: {pr_data.get('commit_message', '')}\n\n"
        f"PR Title: {pr_data.get('pr_title', '')}\n\n"
        f"PR Description:\n{pr_data.get('pr_description', '')}\n\n"
        f"Code Stubs:\n{pr_data.get('code_stubs', '')}"
    )
    st.download_button(
        "⬇️ Download PR Draft",
        data=full_pr,
        file_name=f"pr_draft_issue_{issue_num}.md",
        mime="text/markdown",
        key=f"dl_pr_{issue_num}",
    )


def _render_chat(repo_analysis):
    """Render the RAG-powered chat panel."""
    st.markdown('<div class="section-header"><h2>💬 Ask About the Codebase</h2></div>', unsafe_allow_html=True)
    st.markdown(
        '<div style="font-size:0.85rem;color:#64748b;margin-bottom:1rem;">'
        "Ask anything about the repository. Answers are grounded in the actual code via RAG — "
        "not general LLM knowledge.</div>",
        unsafe_allow_html=True,
    )
    for msg in st.session_state.chat_history:
        if msg["role"] == "user":
            st.markdown(
                f'<div class="chat-msg-user">👤 <b>You:</b> {msg["content"]}</div>',
                unsafe_allow_html=True,
            )
        else:
            st.markdown(
                f'<div class="chat-msg-ai">🤖 <b>Assistant:</b><br>{msg["content"]}</div>',
                unsafe_allow_html=True,
            )

    settings = get_settings()
    col_q, col_send = st.columns([5, 1])
    with col_q:
        user_question = st.text_input(
            "Ask a question",
            placeholder="e.g. Why is this file important? What does the routing system do?",
            label_visibility="collapsed",
            key="chat_input",
        )
    with col_send:
        send_btn = st.button("Send →", key="chat_send", use_container_width=True)

    suggestions = [
        "What are the main entry points?",
        "Which files are most critical?",
        "How does authentication work?",
        "What testing framework is used?",
    ]
    sug_cols = st.columns(len(suggestions))
    for i, sug in enumerate(suggestions):
        with sug_cols[i]:
            if st.button(sug, key=f"sug_{i}", use_container_width=True):
                user_question = sug
                send_btn = True

    if send_btn and user_question.strip():
        st.session_state.chat_history.append({"role": "user", "content": user_question})
        with st.spinner("Searching codebase and generating answer..."):
            try:
                from embeddings import EmbeddingStore as _ES
                embed_store = _ES(
                    persist_dir=settings["chroma_dir"],
                    ollama_base_url=settings["ollama_url"],
                    embed_model=settings["embed_model"],
                )
                llm_client = get_llm_client(settings)
                context_docs = embed_store.search(
                    repo_url=repo_analysis.repo_url,
                    query=user_question,
                    n_results=5,
                )
                answer = ""
                for chunk in llm_client.answer_question(
                    question=user_question,
                    context_docs=context_docs,
                    repo_name=repo_analysis.repo_name,
                    chat_history=st.session_state.chat_history[:-1],
                ):
                    answer += chunk
                st.session_state.chat_history.append({"role": "assistant", "content": answer})
                st.rerun()
            except Exception as e:
                st.session_state.chat_history.append({"role": "assistant", "content": f"Error: {e}"})
                st.rerun()

    if st.session_state.chat_history:
        if st.button("🗑️ Clear Chat", key="clear_chat"):
            st.session_state.chat_history = []
            st.rerun()


# ─────────────────────────────────────────────────────────────────────────────
#  Tab Layout
# ─────────────────────────────────────────────────────────────────────────────
tab_single, tab_multi = st.tabs(["🔍 Single Repo Analysis", "⚖️ Multi-Repo Comparison"])



# ═══════════════════════════════════════════════════════════════════════════
#  TAB 1: Single Repo Analysis
# ═══════════════════════════════════════════════════════════════════════════
with tab_single:

    # ── Input Section ────────────────────────────────────────────────────────
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        repo_url_input = st.text_input(
            "GitHub Repository URL",
            placeholder="https://github.com/owner/repository",
            label_visibility="collapsed",
            key="repo_url_input",
        )
    with col_btn:
        analyze_btn = st.button("🔍 Analyze", use_container_width=True, key="analyze_btn")

    st.markdown('<div class="info-banner">💡 Try: <code>https://github.com/pallets/flask</code> · <code>https://github.com/psf/requests</code> · <code>https://github.com/fastapi/fastapi</code></div>', unsafe_allow_html=True)

    # ── Error display ─────────────────────────────────────────────────────────
    if st.session_state.error:
        st.error(f"❌ {st.session_state.error}")
        if st.button("Clear Error"):
            st.session_state.error = None
            st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    #  Analysis Pipeline
    # ─────────────────────────────────────────────────────────────────────────
    if analyze_btn and repo_url_input.strip():
        repo_url = repo_url_input.strip()
        settings = get_settings()

        # Reset state for new analysis
        st.session_state.analysis_done = False
        st.session_state.repo_analysis = None
        st.session_state.analyzed_issues = []
        st.session_state.raw_issues = []
        st.session_state.chat_history = []
        st.session_state.generated_prs = {}
        st.session_state.error = None
        st.session_state.current_repo_url = repo_url

        # Import modules
        from github_client import GitHubClient, parse_github_url
        from repo_analyzer import RepoAnalyzer
        from embeddings import EmbeddingStore
        from llm import OllamaClient
        from issue_matcher import IssueMatcher

        try:
            # Validate Ollama
            if not _ollama_ok and not settings.get("demo_mode", False):
                raise RuntimeError(
                    "Ollama is not running. Please start it with: `ollama serve`\n"
                    f"Then pull the model: `ollama pull {settings['model']}`\n\n"
                    "💡 Or enable 'Heuristic Demo Mode' in the sidebar to test immediately without Ollama!"
                )

            # Parse URL
            owner, repo_name = parse_github_url(repo_url)

            # Initialize clients
            gh_client = GitHubClient(token=settings["github_token"])
            repo_analyzer = RepoAnalyzer(cache_dir=settings["repos_cache"])
            embed_store = EmbeddingStore(
                persist_dir=settings["chroma_dir"],
                ollama_base_url=settings["ollama_url"],
                embed_model=settings["embed_model"],
            )
            llm_client = get_llm_client(settings)
            matcher = IssueMatcher(gh_client, repo_analyzer, embed_store, llm_client)

            # ── Stage indicator ──
            with st.status("🔄 Analyzing repository...", expanded=True) as status_box:

                # Step 1: Fetch repo metadata (API first, local fallback)
                st.write("📡 Connecting to GitHub...")
                gh_repo = gh_client.get_repo(owner, repo_name)
                st.session_state.gh_repo = gh_repo

                # Step 2: Clone (do this before metadata so local fallback has files)
                st.write("📦 Cloning repository (shallow)...")
                clone_url = f"https://github.com/{owner}/{repo_name}.git"
                clone_path = repo_analyzer.clone_or_pull(
                    repo_url=clone_url,
                    repo_name=f"{owner}_{repo_name}",
                    progress_callback=lambda msg: st.write(f"  {msg}"),
                )
                st.write("✅ Cloned to local cache")

                # Now get metadata — local fallback has clone_path available
                metadata = gh_client.get_repo_metadata(
                    gh_repo,
                    owner=owner,
                    repo_name=repo_name,
                    clone_path=clone_path,
                )
                stars_display = f"{metadata['stars']:,}" if isinstance(metadata['stars'], int) else str(metadata['stars'])
                st.write(f"✅ Found: **{metadata['full_name']}** ({stars_display} ⭐)")
                # Step 3: Parse codebase
                st.write("🔬 Parsing codebase with tree-sitter...")
                repo_analysis = repo_analyzer.analyze(
                    clone_path=clone_path,
                    repo_url=repo_url,
                    repo_name=f"{owner}/{repo_name}",
                    progress_callback=lambda msg: st.write(f"  {msg}"),
                )
                repo_analysis.architecture_summary = ""  # Will fill below
                st.write(f"✅ Parsed {repo_analysis.total_files} files, {repo_analysis.total_lines:,} lines")

                # Step 4: Embed files
                already_indexed = embed_store.collection_exists(repo_url)
                if already_indexed:
                    st.write("⚡ Using cached embeddings (already indexed)")
                else:
                    st.write("🧮 Embedding file summaries into ChromaDB...")
                    embed_store.index_files(
                        repo_url=repo_url,
                        files=repo_analysis.files,
                        progress_callback=lambda msg: st.write(f"  {msg}"),
                    )
                    st.write(f"✅ Indexed {len(repo_analysis.files)} files")

                # Step 5: Architecture explanation (streaming)
                st.write("🧠 Generating architecture explanation...")
                key_files = list(repo_analysis.files.values())[:10]
                key_files_summary = "\n".join(
                    f"- {f.path}: {', '.join(f.functions[:5] + f.classes[:3])}"
                    for f in key_files if f.functions or f.classes
                )
                arch_text = ""
                for chunk in llm_client.explain_architecture(
                    repo_name=f"{owner}/{repo_name}",
                    readme=metadata["readme"],
                    file_tree=repo_analysis.file_tree,
                    languages=repo_analysis.languages,
                    entry_points=repo_analysis.entry_points,
                    key_files_summary=key_files_summary,
                ):
                    arch_text += chunk
                repo_analysis.architecture_summary = arch_text
                st.write("✅ Architecture explained")

                # Step 6: Fetch issues (GitHub API first, local codebase fallback)
                st.write("🐛 Fetching beginner-friendly issues...")
                raw_issues = gh_client.get_issues(
                    repo=gh_repo,
                    clone_path=clone_path,
                    owner=owner,
                    repo_name=repo_name,
                    max_issues=20,
                )
                st.session_state.raw_issues = raw_issues
                if not raw_issues:
                    st.warning("⚠️ No open issues found in this repo.")
                else:
                    source_label = "GitHub API" if not gh_client.rate_limited else "local codebase scan"
                    st.write(f"✅ Found {len(raw_issues)} candidate issues (via {source_label})")

                # Step 7: Analyze & rank issues
                if raw_issues:
                    st.write("🏆 Analyzing and ranking issues...")
                    analyzed_issues = matcher.analyze_issues(
                        repo_analysis=repo_analysis,
                        raw_issues=raw_issues,
                        gh_repo=gh_repo,
                        progress_callback=lambda msg: st.write(f"  {msg}"),
                    )
                    st.session_state.analyzed_issues = analyzed_issues
                    st.write(f"✅ Ranked {len(analyzed_issues)} issues by contribution readiness")

                st.session_state.repo_analysis = repo_analysis
                st.session_state.analysis_done = True

                status_box.update(
                    label=f"✅ Analysis complete — {owner}/{repo_name}",
                    state="complete",
                    expanded=False,
                )

        except ValueError as e:
            st.session_state.error = str(e)
            st.rerun()
        except RuntimeError as e:
            st.session_state.error = str(e)
            st.rerun()
        except Exception as e:
            st.session_state.error = f"Unexpected error: {type(e).__name__}: {e}"
            logger.exception("Analysis pipeline error")
            st.rerun()

    # ─────────────────────────────────────────────────────────────────────────
    #  Results Display
    # ─────────────────────────────────────────────────────────────────────────
    if st.session_state.analysis_done and st.session_state.repo_analysis:
        repo_analysis = st.session_state.repo_analysis
        analyzed_issues = st.session_state.analyzed_issues

        # ── Repo summary metrics ──────────────────────────────────────────────
        st.markdown("---")
        parts = repo_analysis.repo_name.split("/")
        repo_display = repo_analysis.repo_name

        m1, m2, m3, m4, m5 = st.columns(5)
        with m1:
            st.markdown(f'<div class="metric-mini"><div class="value">{repo_analysis.total_files}</div><div class="label">Files Parsed</div></div>', unsafe_allow_html=True)
        with m2:
            st.markdown(f'<div class="metric-mini"><div class="value">{repo_analysis.total_lines:,}</div><div class="label">Lines of Code</div></div>', unsafe_allow_html=True)
        with m3:
            top_lang = max(repo_analysis.languages, key=repo_analysis.languages.get) if repo_analysis.languages else "—"
            st.markdown(f'<div class="metric-mini"><div class="value">{top_lang}</div><div class="label">Primary Language</div></div>', unsafe_allow_html=True)
        with m4:
            st.markdown(f'<div class="metric-mini"><div class="value">{len(analyzed_issues)}</div><div class="label">Issues Ranked</div></div>', unsafe_allow_html=True)
        with m5:
            if analyzed_issues:
                avg_score = sum(i.readiness.total_score for i in analyzed_issues) / len(analyzed_issues)
                st.markdown(f'<div class="metric-mini"><div class="value">{avg_score:.0f}</div><div class="label">Avg Readiness</div></div>', unsafe_allow_html=True)
            else:
                st.markdown('<div class="metric-mini"><div class="value">—</div><div class="label">Avg Readiness</div></div>', unsafe_allow_html=True)

        st.markdown("---")

        # ── Architecture + Graph side by side ────────────────────────────────
        st.markdown('<div class="section-header"><h2>🏗️ Architecture Overview</h2></div>', unsafe_allow_html=True)

        col_arch, col_graph = st.columns([1, 1], gap="large")

        with col_arch:
            with st.container():
                st.markdown(
                    f'<div class="glass-card" style="min-height:450px;overflow-y:auto;">'
                    f'{repo_analysis.architecture_summary}</div>',
                    unsafe_allow_html=True,
                )

        with col_graph:
            st.markdown("**📊 Module Dependency Graph** — nodes sized by complexity, edges show imports")
            _render_dependency_graph(repo_analysis, analyzed_issues)

        # ── Issues Section ────────────────────────────────────────────────────
        st.markdown("---")
        if not analyzed_issues:
            st.info("ℹ️ No open issues found in this repository. Try a repo with active issues!")
        else:
            st.markdown(
                f'<div class="section-header"><h2>🏆 Issues Ranked by Contribution Readiness</h2></div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div style="font-size:0.85rem;color:#64748b;margin-bottom:1rem;">'
                f'Showing {len(analyzed_issues)} issues · Sorted easiest → hardest · '
                f'Score combines: file scope (30%), test coverage (20%), code stability (20%), '
                f'issue freshness (20%), description clarity (10%)'
                f'</div>',
                unsafe_allow_html=True,
            )

            _render_issues(analyzed_issues, repo_analysis, st.session_state.raw_issues)

        # ── Chat Section ──────────────────────────────────────────────────────
        st.markdown("---")
        _render_chat(repo_analysis)





# ═══════════════════════════════════════════════════════════════════════════
#  TAB 2: Multi-Repo Comparison
# ═══════════════════════════════════════════════════════════════════════════
with tab_multi:
    st.markdown("### ⚖️ Compare Repos for Beginner-Friendliness")
    st.markdown(
        '<div style="font-size:0.85rem;color:#64748b;margin-bottom:1rem;">'
        "Paste 2–3 GitHub repo URLs to get a side-by-side comparison. "
        "Useful for picking your first Hacktoberfest repo to contribute to.</div>",
        unsafe_allow_html=True,
    )

    multi_url1 = st.text_input("Repo URL 1", placeholder="https://github.com/owner/repo1", key="multi_url1")
    multi_url2 = st.text_input("Repo URL 2", placeholder="https://github.com/owner/repo2", key="multi_url2")
    multi_url3 = st.text_input("Repo URL 3 (optional)", placeholder="https://github.com/owner/repo3", key="multi_url3")

    compare_btn = st.button("⚖️ Compare Repos", key="compare_btn")

    if compare_btn:
        urls = [u.strip() for u in [multi_url1, multi_url2, multi_url3] if u.strip()]
        if len(urls) < 2:
            st.error("Please provide at least 2 repo URLs to compare.")
        else:
            from github_client import GitHubClient, parse_github_url
            from repo_analyzer import RepoAnalyzer
            from embeddings import EmbeddingStore
            from llm import OllamaClient
            from issue_matcher import IssueMatcher

            settings = get_settings()
            multi_results = []

            with st.status("Analyzing repositories for comparison...", expanded=True) as mstatus:
                for url in urls:
                    try:
                        owner, repo_name = parse_github_url(url)
                        st.write(f"📡 Fetching {owner}/{repo_name}...")

                        gh_client = GitHubClient(token=settings["github_token"])
                        repo_analyzer = RepoAnalyzer(cache_dir=settings["repos_cache"])
                        embed_store = EmbeddingStore(
                            persist_dir=settings["chroma_dir"],
                            ollama_base_url=settings["ollama_url"],
                            embed_model=settings["embed_model"],
                        )
                        llm_client = get_llm_client(settings)

                        gh_repo = gh_client.get_repo(owner, repo_name)
                        metadata = gh_client.get_repo_metadata(gh_repo)
                        clone_path = repo_analyzer.clone_or_pull(
                            repo_url=metadata["clone_url"],
                            repo_name=f"{owner}_{repo_name}",
                        )
                        repo_analysis = repo_analyzer.analyze(
                            clone_path=clone_path,
                            repo_url=url,
                            repo_name=f"{owner}/{repo_name}",
                        )

                        # Quick embed (without full LLM analysis)
                        if not embed_store.collection_exists(url):
                            embed_store.index_files(url, repo_analysis.files, batch_size=20)

                        raw_issues = gh_client.get_issues(gh_repo, max_issues=10)
                        matcher = IssueMatcher(gh_client, repo_analyzer, embed_store, llm_client)

                        if raw_issues:
                            analyzed = matcher.analyze_issues(
                                repo_analysis=repo_analysis,
                                raw_issues=raw_issues,
                                gh_repo=gh_repo,
                            )
                            avg_score = sum(i.readiness.total_score for i in analyzed if i.readiness) / max(len(analyzed), 1)
                            beginner_count = sum(1 for i in analyzed if i.readiness and i.readiness.total_score >= 60)
                        else:
                            avg_score = 0
                            beginner_count = 0
                            analyzed = []

                        multi_results.append({
                            "name": f"{owner}/{repo_name}",
                            "url": url,
                            "stars": metadata["stars"],
                            "languages": metadata["languages"],
                            "avg_readiness": avg_score,
                            "issue_count": len(analyzed),
                            "beginner_count": beginner_count,
                            "architecture_summary": repo_analysis.architecture_summary or "",
                            "analyzed_issues": analyzed,
                        })
                        st.write(f"✅ {owner}/{repo_name}: avg readiness {avg_score:.1f}, {beginner_count} beginner-ready issues")

                    except Exception as e:
                        st.write(f"❌ Failed to analyze {url}: {e}")
                        multi_results.append({"name": url, "error": str(e)})

                mstatus.update(label="✅ Comparison complete!", state="complete", expanded=False)

            st.session_state.multi_done = True
            st.session_state.multi_analyses = multi_results

    if st.session_state.multi_done and st.session_state.multi_analyses:
        results = [r for r in st.session_state.multi_analyses if "error" not in r]
        if results:
            winner = max(results, key=lambda x: x["avg_readiness"])

            st.markdown("---")
            st.markdown("### 🏅 Comparison Results")

            cols = st.columns(len(results))
            for i, (col, repo) in enumerate(zip(cols, results)):
                with col:
                    is_winner = repo["name"] == winner["name"]
                    card_class = "compare-card winner" if is_winner else "compare-card"
                    score_color = "#22c55e" if is_winner else "#f97316"
                    winner_badge = "🏆 Most Beginner-Friendly" if is_winner else ""
                    st.markdown(
                        f'<div class="{card_class}">'
                        f'<div class="repo-name">{repo["name"]}</div>'
                        f'{"<div style=\"color:#22c55e;font-weight:700;font-size:0.8rem;margin-bottom:0.5rem;\">🏆 WINNER</div>" if is_winner else ""}'
                        f'<div class="big-score" style="color:{score_color};">{repo["avg_readiness"]:.1f}</div>'
                        f'<div style="font-size:0.72rem;color:#64748b;margin:0.25rem 0 0.75rem;">Avg Readiness Score</div>'
                        f'<div style="font-size:0.82rem;line-height:1.8;">'
                        f'⭐ {repo["stars"]:,} stars<br>'
                        f'🐛 {repo["issue_count"]} issues analyzed<br>'
                        f'✅ {repo["beginner_count"]} beginner-ready<br>'
                        f'🔤 {", ".join(list(repo["languages"].keys())[:2])}'
                        f'</div></div>',
                        unsafe_allow_html=True,
                    )

            # LLM comparison narrative
            st.markdown("---")
            st.markdown("### 🤖 AI Recommendation")
            settings = get_settings()
            if _ollama_ok or settings.get("demo_mode", False):
                with st.spinner("Generating comparison narrative..."):
                    try:
                        llm_client = get_llm_client(settings)
                        narrative = llm_client.compare_repos(results)
                        st.markdown(narrative)
                    except Exception as e:
                        st.warning(f"Could not generate narrative: {e}")
            else:
                st.warning("Ollama not running — narrative unavailable. Enable Heuristic Demo Mode in sidebar.")


# ─────────────────────────────────────────────────────────────────────────────
#  Footer
# ─────────────────────────────────────────────────────────────────────────────
st.markdown("---")
st.markdown(
    '<div style="text-align:center;padding:1.5rem 0;color:#475569;font-size:0.8rem;">'
    "🎃 <b>First Issue Finder</b> · Built for Hacktoberfest 2024 · "
    "Powered by <a href='https://huggingface.co/Qwen/Qwen2.5-Coder-7B-Instruct' style='color:#f97316;'>Qwen2.5-Coder</a> via "
    "<a href='https://ollama.ai' style='color:#f97316;'>Ollama</a> · "
    "All analysis runs locally · MIT License"
    "</div>",
    unsafe_allow_html=True,
)
