# 🎃 First Issue Finder — Complete Setup Guide

> A Hacktoberfest contributor onboarding agent that reads any public GitHub repo, explains its architecture, finds beginner-friendly issues, ranks them by real difficulty, and generates a step-by-step fix plan + draft PR skeleton.

---

## Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| **Python** | 3.10 or 3.11 | 3.12 works but some deps may warn |
| **Git** | any modern version | Required for cloning repos |
| **Ollama** | latest | ollama.com — runs the LLM locally |
| **~8 GB RAM** | — | For qwen2.5-coder:7b; use 3b model on 4 GB systems |
| **~6 GB disk** | — | For model weights + ChromaDB |

---

## Step 1 — Install Ollama

### Windows
1. Download the installer from **https://ollama.com/download**
2. Run the `.exe` installer and follow the prompts
3. Ollama will start automatically as a background service after install

### macOS
```bash
brew install ollama
```

### Linux
```bash
curl -fsSL https://ollama.com/install.sh | sh
```

---

## Step 2 — Pull the Required Models

Open a terminal and run:

```bash
# Main reasoning model (~5 GB download)
ollama pull qwen2.5-coder:7b

# Lighter alternative if RAM is limited (~2 GB)
ollama pull qwen2.5-coder:3b

# Embedding model for semantic search — REQUIRED (~274 MB)
ollama pull nomic-embed-text
```

Verify:
```bash
ollama list
# Should show: qwen2.5-coder:7b, nomic-embed-text
```

---

## Step 3 — Open the Project Directory

```powershell
cd d:\Hacktober
```

Or if cloning fresh:
```bash
git clone https://github.com/your-username/first-issue-finder.git
cd first-issue-finder
```

---

## Step 4 — Create a Python Virtual Environment

```powershell
# Windows PowerShell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

```bash
# macOS / Linux
python3 -m venv .venv
source .venv/bin/activate
```

> **Note (Windows):** If you get an execution policy error, run:
> `Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned`
> then retry the activate command.

---

## Step 5 — Install Python Dependencies

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

### tree-sitter build fails?

```bash
pip install tree-sitter==0.20.4 tree-sitter-python==0.20.4 tree-sitter-javascript==0.20.1
```

If it still fails, that's fine — the app automatically falls back to Python `ast` + regex parsing with no loss of core functionality.

---

## Step 6 — Configure Environment Variables

```powershell
copy .env.example .env
```

Open `.env` in any text editor and fill in:

```dotenv
# Optional but strongly recommended (60 req/hr → 5000 req/hr)
GITHUB_TOKEN=ghp_your_personal_access_token_here

# Ollama — defaults work if Ollama runs on this machine
OLLAMA_BASE_URL=http://localhost:11434
OLLAMA_MODEL=qwen2.5-coder:7b
OLLAMA_EMBED_MODEL=nomic-embed-text

# Storage directories (created automatically on first run)
REPOS_CACHE_DIR=./repos_cache
CHROMA_PERSIST_DIR=./chroma_db
```

### How to get a GitHub Personal Access Token

1. Go to **https://github.com/settings/tokens**
2. Click **"Generate new token"**
3. Select scope: ✅ `public_repo`
4. Copy the generated token (starts with `ghp_`)
5. Paste it as the `GITHUB_TOKEN` value in your `.env` file

> **Without a token:** GitHub rate-limits unauthenticated requests to 60/hour.
> When rate-limited, the app automatically falls back to scanning the locally cloned codebase for TODOs, missing tests, and other contribution opportunities — so it still works.

---

## Step 7 — Ensure Ollama is Running

On Windows, Ollama auto-starts after install. To verify, open:
**http://localhost:11434** — you should see `Ollama is running`.

If it's not running, start it manually:
```bash
ollama serve
```

---

## Step 8 — Launch the App

```bash
streamlit run app.py
```

The browser will open automatically at **http://localhost:8501**

---

## How to Use the App

### Single Repo Analysis

1. Paste a GitHub URL in the input box, for example:
   - `https://github.com/pallets/flask`
   - `https://github.com/psf/requests`
   - `https://github.com/fastapi/fastapi`
   - `https://github.com/tiangolo/sqlmodel`

2. Click **Analyze**

3. The pipeline runs automatically:
   | Step | What happens |
   |------|-------------|
   | 📡 Connect | GitHub API fetch (or direct git clone if rate-limited) |
   | 📦 Clone | Shallow clone cached in `./repos_cache/` |
   | 🔬 Parse | tree-sitter AST parsing of all source files |
   | 🧮 Embed | ChromaDB semantic index built from file summaries |
   | 🧠 Explain | Ollama generates architecture overview |
   | 🐛 Issues | Beginner-friendly issues fetched & ranked |
   | 🏆 Display | Results shown sorted easiest → hardest |

4. For each ranked issue:
   - **Readiness Score** — weighted breakdown of 5 factors (scope, tests, stability, freshness, clarity)
   - **AI Explanation** — click to generate a plain-language explanation of what the issue requires
   - **Fix Plan** — click to generate a step-by-step implementation guide
   - **Draft PR** — click to generate branch name, commit message, PR title, description, and code stubs

5. **Chat panel** — Ask anything about the codebase (RAG-powered, grounded in actual code)

### Multi-Repo Comparison

Switch to the **⚖️ Multi-Repo Comparison** tab to compare 2–3 repos side-by-side.
Useful for deciding which Hacktoberfest repo to start contributing to.

---

## Demo Mode — No Ollama Required

If Ollama is not installed or not running, the sidebar shows an orange warning.
Enable the **"Heuristic Demo Mode"** checkbox.

In demo mode:
- The full pipeline still runs (cloning, parsing, dependency graph, readiness scoring)
- Architecture summaries, issue explanations, fix plans, and PR drafts are generated using **heuristic rules** instead of LLM calls
- No GPU or model download required — works on any machine
- Great for testing, demos, or CI environments

---

## Troubleshooting

### `ollama: command not found`
Re-install Ollama from https://ollama.com/download and make sure it's added to PATH.

### `Model 'qwen2.5-coder:7b' not found in Ollama`
```bash
ollama pull qwen2.5-coder:7b
```

### `Cannot connect to Ollama`
Start it: `ollama serve`
Or on Windows: check the system tray for the Ollama icon.

### `ModuleNotFoundError: No module named 'streamlit'`
Your virtual environment is not activated. Run:
```powershell
.\.venv\Scripts\Activate.ps1   # Windows
```
```bash
source .venv/bin/activate       # Mac/Linux
```

### GitHub `403 Forbidden` / Rate Limit errors
Add a GitHub PAT to your `.env` file (see Step 6). The app will still function using local codebase scanning even without a token.

### `chromadb` errors or crashes
```bash
pip install chromadb --upgrade
```

### Very slow first analysis
First run: clones + parses + embeds the entire repo (1–3 min depending on size).
Subsequent analyses of the same repo use the cache and are near-instant.

### `tree-sitter` build errors on Windows
```bash
pip install --only-binary :all: tree-sitter
```
The app will auto-fallback if tree-sitter can't load.

---

## Project Structure

```
d:\Hacktober\
├── app.py              ← Streamlit UI + pipeline orchestration
├── github_client.py    ← GitHub API fetch + local codebase fallback
├── repo_analyzer.py    ← Git clone + tree-sitter/AST parsing
├── embeddings.py       ← ChromaDB vector store + Ollama embeddings
├── llm.py              ← Ollama LLM client (streaming + demo mode)
├── issue_matcher.py    ← Issue scoring + file relevance matching
├── readiness_score.py  ← 5-factor weighted readiness scoring
├── requirements.txt    ← Python dependencies
├── .env.example        ← Environment variable template
├── .env                ← Your local config (not committed to git)
├── repos_cache/        ← Cloned repos (auto-created)
└── chroma_db/          ← Vector embeddings (auto-created)
```

---

## Hardware Requirements

| Setup | RAM | Model | Est. Speed |
|-------|-----|-------|-----------|
| Minimum | 4 GB | `qwen2.5-coder:3b` | ~30 sec/analysis |
| Recommended | 8 GB | `qwen2.5-coder:7b` | ~45 sec/analysis |
| Optimal | 16 GB | `qwen2.5-coder:7b` | ~20 sec/analysis |
| GPU (CUDA / Metal) | any | any | 3–5× faster |

> For low-RAM machines, set `OLLAMA_MODEL=qwen2.5-coder:3b` in your `.env`.

---

*Built for Hacktoberfest 2024 · Runs 100% locally on your machine · No data sent to external servers · MIT License*
