# Friday Router

Austin's intelligent model routing skill for OpenClaw. Routes tasks to the right LLM by tier — capable by default, down-routes to cheaper models only when the task is clearly simple.

## Default behavior

**Session default:** OpenRouter Claude Sonnet 4 — capable of basic coding and complex tasks.

The router **down-routes** to cheaper/faster models (e.g. Gemini 2.5 Flash) only when the task is clearly simple (FAST tier). So you start capable by default; simple tasks save cost. When the skill is installed, OpenClaw's default model is set to Claude Sonnet 4 so every new session is capable by default.

---

## Orchestrator flow (task delegation)

The **main agent (Sonnet)** does not do user tasks itself. For every user **task** (code, research, check, build, etc.):

1. Run the router: `python scripts/router.py spawn --json "<user message>"` and parse the JSON output.
2. Call **sessions_spawn** with the `task` and `model` (and any other params) from the router.
3. The sub-agent does the work; you forward or summarize its result.

**Exception:** Meta-questions ("what model are you?", "how does routing work?") you answer yourself. See the skill's SKILL.md for full steps.

---

## Quick start

```bash
# Install (from skill directory or via clawhub)
npm install -g clawhub
clawhub install friday-router

# Show session default model
python scripts/router.py default

# Classify a task
python scripts/router.py classify "your task description"
```

---

## Features

- **Capable by default** — OpenRouter Claude Sonnet 4 for new sessions; simple tasks down-route to Gemini 2.5 Flash
- Fixed scoring bugs from original intelligent-router (simple indicators, agentic bump, vision priority, code keywords, confidence)
- 7 tiers: FAST, REASONING, CREATIVE, RESEARCH, CODE, QUALITY, VISION
- OpenClaw integration: main agent delegates via `spawn --json` + **sessions_spawn**; router provides model + task params
- Config-driven: `config.json` for models and routing rules; `default_model` for session default

---

## Models

| Tier | Model | Cost/M (in/out) |
|------|-------|-----------------|
| **Default** | OpenRouter Claude Sonnet 4 | $3 / $15 |
| FAST | Gemini 2.5 Flash (OpenRouter) | $0.30 / $2.50 |
| REASONING | GLM-5 | $0.10 / $0.10 |
| CREATIVE | Kimi k2.5 | $0.20 / $0.20 |
| RESEARCH | Grok Fast | $0.10 / $0.10 |
| CODE | DeepSeek Coder V2 | $0.14 / $0.28 |
| QUALITY | OpenRouter Claude Sonnet 4 | $3.00 / $15.00 |
| VISION | GPT-4o | $2.50 / $10.00 |

**Fallbacks:** FAST → Gemini 1.5 Flash, Haiku; QUALITY → Claude 3.5 Sonnet, GPT-4o; CODE → Qwen 2.5 Coder; REASONING → Minimax 2.5.

---

## CLI usage

Run from the skill directory (e.g. `workspace/skills/friday-router` or `friday-router`):

```bash
# Session default model (capable by default)
python scripts/router.py default

# Classify a task and get recommended model
python scripts/router.py classify "fix lint errors in utils.js"

# Detailed scoring breakdown
python scripts/router.py score "build a React auth system"

# Cost estimate
python scripts/router.py cost "design a landing page"

# OpenClaw spawn params (human-readable)
python scripts/router.py spawn "research the best LLMs"

# Spawn params as JSON (includes gatewayToken/gatewayPort from openclaw.json; parse and pass to sessions_spawn)
python scripts/router.py spawn --json "research the best LLMs"

# List all configured models
python scripts/router.py models
```

---

## In-code usage

```python
from scripts.router import FridayRouter

router = FridayRouter()

# Session default model (e.g. for display or config)
default = router.get_default_model()  # → model dict or None

# Classify task → tier string
tier = router.classify_task("check server status")
# → "FAST"

# Full recommendation (tier, model, fallback, reasoning)
result = router.recommend_model("build authentication system")
# → {"tier": "CODE", "model": {...}, "fallback": {...}, "reasoning": "..."}

# Spawn params for OpenClaw sub-agent
spawn_params = router.spawn_agent("fix this bug", label="bugfix")
# → {"params": {"task": "...", "model": "deepseek-ai/deepseek-coder-v2", "sessionTarget": "isolated", "label": "bugfix"}, "recommendation": {...}}

# Cost estimate
cost = router.estimate_cost("design landing page")
# → {"tier": "CREATIVE", "model": "Kimi-k2.5", "cost": 0.0007, "currency": "USD"}
```

---

## Tier detection

| Tier | Example keywords |
|------|------------------|
| **FAST** | check, get, list, show, status, monitor, fetch, simple |
| **REASONING** | prove, logic, analyze, derive, math, step by step |
| **CREATIVE** | creative, write, story, design, UI, UX, frontend, website |
| **RESEARCH** | research, find, search, lookup, web, information |
| **CODE** | code, function, debug, fix, implement, refactor, test, React, JWT |
| **QUALITY** | complex, architecture, design, system, comprehensive |
| **VISION** | image, picture, photo, screenshot, visual |

- **Vision** has priority: if vision keywords are present, task is VISION regardless of other keywords.
- **Agentic** tasks (multi-step, e.g. "first X then Y", "step 1") are bumped to at least CODE.

---

## Examples

```bash
# Simple monitoring → FAST (Gemini 2.5 Flash)
python scripts/router.py classify "check server status"

# Code task → CODE (DeepSeek Coder)
python scripts/router.py classify "fix lint errors in utils.js"

# Multi-step build → CODE (agentic)
python scripts/router.py classify "build React auth with JWT, tests, CI"

# Mathematical proof → REASONING (GLM-5)
python scripts/router.py classify "prove sqrt(2) is irrational"

# Design → CREATIVE (Kimi k2.5)
python scripts/router.py classify "design a beautiful landing page"

# Research → RESEARCH (Grok Fast)
python scripts/router.py classify "find information about GPT-5"

# Vision → VISION (GPT-4o)
python scripts/router.py classify "analyze this screenshot"
```

---

## Configuration

- **`config.json`** — Model list and `routing_rules` per tier; optional **`default_model`** (e.g. `openrouter/anthropic/claude-sonnet-4`) for session default.
- Router loads `config.json` from the parent of `scripts/` (skill root). Use `FridayRouter(config_path="...")` to override.

---

## What changed from original (intelligent-router)

| Issue | Fix |
|-------|-----|
| Simple indicators inverted (high match = complex) | High simple keyword match → FAST tier |
| Agentic tasks not bumping tier | Multi-step tasks bump to CODE |
| Vision tasks misclassified | Vision keywords take priority |
| Code keywords missed | Added React, JWT, API, etc. |
| Confidence always low | Varies with keyword match strength |

---

## License / author

Austin. Part of the OpenClaw skills ecosystem.
