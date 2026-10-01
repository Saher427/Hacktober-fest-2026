# 🎃 First Issue Finder — Demo Script

**Suggested duration: 2–3 minutes**  
Use this as your judge/audience walkthrough guide.

---

## Setup Before Demo

```bash
# Terminal 1: Ollama must be running
ollama serve

# Terminal 2: Start the app
streamlit run app.py
```

Open **http://localhost:8501**

Pre-warm the cache by analyzing `https://github.com/psf/requests` before the live demo — this makes the demo snappy.

---

## 🎬 Demo Script

---

### ⏱️ 0:00 — Hook (20 seconds)

> "Every Hacktoberfest, thousands of developers want to contribute to open source for the first time — but they don't know where to start. The issues labeled 'good first issue' are often anything but. We built an AI agent that tells you the truth."

**[Show the landing page — dark glassmorphism design, Hacktoberfest branding]**

---

### ⏱️ 0:20 — Paste URL and Analyze (30 seconds)

> "I paste the URL of a real open-source project — let's use `psf/requests` — and hit Analyze."

**[Type `https://github.com/psf/requests` in the input box, click Analyze]**

> "Watch the staged progress: cloning, parsing with tree-sitter, embedding into ChromaDB, fetching issues, ranking with the LLM..."

**[Point out the status box with live progress messages]**

> "And because we already cached this repo — the second time is instant."

---

### ⏱️ 0:50 — Architecture Map (30 seconds)

**[Scroll to the Architecture section — the interactive graph is visible]**

> "First, look at this — an interactive dependency graph of the entire codebase. Every node is a source file, sized by complexity. Edges show which files import which."

**[Hover over nodes to show tooltips]**

> "The orange-bordered nodes? Those are files that open issues are touching. You can immediately see which parts of the codebase are 'hot' for contributions."

**[Scroll to architecture explanation text on the left]**

> "And here's the architecture explained in plain English by Qwen2.5-Coder — what the project does, how it's structured, the entry points a newcomer should read first. Generated locally, zero data leaves this machine."

---

### ⏱️ 1:20 — Ranked Issue + Readiness Score (40 seconds)

**[Scroll to Issues section — show the ranked list]**

> "Here are the open issues, sorted from easiest to hardest — not by label, but by our Contribution Readiness Score."

**[Click to expand the #1 ranked issue]**

> "This issue scores 78 out of 100. But what's important is WHY. Look at the breakdown:"

**[Point to the Readiness Score tab with the factor bars]**

> "It touches only 2 files — great scope. Those files have existing tests — easy to verify. The code is stable — low merge conflict risk. The issue is recent and unassigned — nobody's claimed it. And the description is detailed — clear requirements."

> "Every factor is shown with its weight. No black box."

---

### ⏱️ 2:00 — Fix Plan (20 seconds)

**[Click the Fix Plan tab]**

> "Click to the Fix Plan tab — a numbered, concrete plan. Step 1: fork and clone. Step 2: read these specific functions. Step 3: modify exactly this file at this function. Step 4: run these tests."

> "A first-time contributor can follow this without guessing."

---

### ⏱️ 2:20 — Draft PR Generator (25 seconds)

**[Click 'Generate Draft PR' button]**

> "Now hit Generate Draft PR."

**[Wait for generation, then scroll through the PR]**

> "Boom — a branch name in git-flow style, a commit message following Conventional Commits, a full PR description with checkboxes, and actual code stubs as diff blocks — clearly marked as starting points."

**[Click Download PR Draft button]**

> "Download it as a Markdown file, paste it into GitHub."

---

### ⏱️ 2:45 — RAG Chat (15 seconds)

**[Scroll to the chat section]**

**[Type: "What does the Session object do and why is it important?"]**

> "Finally, a follow-up chat — but it's RAG-powered. The answer is grounded in the actual cloned code, not hallucinated. Watch it cite specific files and functions."

---

### ⏱️ 3:00 — Wrap Up

> "Every part of this runs locally. No API keys except an optional GitHub token. No data leaves your machine. Built with Qwen2.5-Coder 7B via Ollama, ChromaDB for vector storage, and Streamlit for the UI."

> "For Hacktoberfest, this means anyone can go from 'I want to contribute' to 'I have a concrete plan and a draft PR' in under 3 minutes."

---

## 💡 Bonus: Multi-Repo Comparison (if time allows)

**[Click Multi-Repo Comparison tab]**

> "Paste two or three repo URLs side by side — it compares them on readiness score, beginner-friendly issue count, and generates a recommendation. Great for picking your first repo."

---

## 📝 Key Messages for Judges

1. **Real pipeline** — not a prototype. Actual tree-sitter parsing, ChromaDB embeddings, Ollama inference.
2. **Transparent scoring** — readiness score shows factors, not a black box.
3. **Runs locally** — privacy by design. All data stays on your machine.
4. **Qwen2.5-Coder** — Apache 2.0 open-weight model, cited clearly.
5. **Caching** — re-analysis is instant; clone, embeddings, and LLM outputs all cached per-repo.
