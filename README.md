# IntentRouter | OpenClaw Skill

**Intelligent LLM routing for OpenClaw.** Classifies tasks by intent and routes each to the optimal model, with input validation and prompt-injection protection.

**v1.8.0 — Identity fix + security hardening.** Resolved naming inconsistency (formerly agent-swarm/friday-router, now consistently IntentRouter). Added `validate_task_string` input validation and prompt-injection rejection. Removed gateway auth secret exposure.

IntentRouter analyzes your OpenClaw tasks and routes them to the best LLM for the job, then delegates work to subagents. You save tokens (orchestrator stays on a cheap model; only the task runs on the matched model) and get better results -- MiniMax 2.5 for code, Kimi k2.5 for creative, Grok Fast for research.

## Requirements

- **OpenRouter** -- All model delegation uses OpenRouter (`openrouter/...` prefix). Configure OpenClaw with an OpenRouter API key so one auth profile covers every model.

## Default behavior

**Session default / orchestrator:** Gemini 2.5 Flash (`openrouter/google/gemini-2.5-flash`) -- fast, cheap, reliable at tool-calling.

The router delegates tasks to tier-specific sub-agents (Kimi for creative, MiniMax 2.5 for code, etc.) via `sessions_spawn`. Simple tasks (check, status, list) down-route to Gemini 2.5 Flash.

---

## Orchestrator flow (task delegation)

The **main agent (Gemini 2.5 Flash)** does not do user tasks itself. For every user **task** (code, research, write, build, etc.):

1. Run IntentRouter: `python scripts/router.py spawn --json "<user message>"` and parse the JSON.
2. Call **sessions_spawn** with the `task` and `model` from the router output (use the exact `model` value).
3. Forward the sub-agent's result to the user.

**Example:**
```
router: {"task":"write a poem","model":"openrouter/moonshotai/kimi-k2.5","sessionTarget":"isolated"}
-> sessions_spawn(task="write a poem", model="openrouter/moonshotai/kimi-k2.5", sessionTarget="isolated")
-> Forward Kimi k2.5's poem to user. Say "Using: Kimi k2.5".
```

**Exception:** Meta-questions ("what model are you?") you answer yourself.

---

## Quick start

```bash
npm install -g clawhub
clawhub install intent-router

python scripts/router.py default
python scripts/router.py classify "your task description"
```

---

## Features

- **Orchestrator** -- Gemini 2.5 Flash delegates to tier-specific sub-agents via `sessions_spawn`
- **Input validation** -- `validate_task_string` rejects empty, overly long, and prompt-injection inputs
- **Prompt-injection rejection** -- patterns like "ignore previous instructions" are blocked before routing
- Fixed scoring bugs from original intelligent-router
- 7 tiers: FAST, REASONING, CREATIVE, RESEARCH, CODE, QUALITY, VISION
- All models via OpenRouter (single API key)
- Config-driven: `config.json` for models and routing rules
- **Security-focused** -- No gateway auth secret exposure, no process management

---

## Models

| Tier | Model | Cost/M (in/out) |
|------|-------|-----------------|
| **Default / orchestrator** | Gemini 2.5 Flash | $0.30 / $2.50 |
| FAST | Gemini 2.5 Flash | $0.30 / $2.50 |
| REASONING | GLM-5 | $0.10 / $0.10 |
| CREATIVE | Kimi k2.5 | $0.20 / $0.20 |
| RESEARCH | Grok Fast | $0.10 / $0.10 |
| CODE | MiniMax 2.5 | $0.10 / $0.10 |
| QUALITY | GLM 4.7 Flash | $0.06 / $0.40 |
| VISION | GPT-4o | $2.50 / $10.00 |

**Fallbacks:** FAST -> Gemini 1.5 Flash, Haiku; QUALITY -> GLM 4.7, Sonnet 4, GPT-4o; CODE -> Qwen Coder; REASONING -> Minimax 2.5.

---

## CLI usage

```bash
python scripts/router.py default                          # Show default model
python scripts/router.py classify "fix lint errors"        # Classify -> tier + model
python scripts/router.py score "build a React auth system" # Detailed scoring
python scripts/router.py cost "design a landing page"      # Cost estimate
python scripts/router.py spawn "research best LLMs"        # Spawn params (human)
python scripts/router.py spawn --json "research best LLMs" # JSON for sessions_spawn
python scripts/router.py models                            # List all models
```

**Note:** Gateway auth management is not included in this skill. Use the separate `gateway-guard` skill if you need gateway auth checking or management.

---

## In-code usage

```python
from scripts.router import IntentRouter, validate_task_string

# Validate input first
is_valid, error = validate_task_string("fix the login bug")
assert is_valid

router = IntentRouter()

default = router.get_default_model()
tier = router.classify_task("check server status")        # -> "FAST"
result = router.recommend_model("build auth system")       # -> {tier, model, fallback, reasoning}
spawn = router.spawn_agent("fix this bug", label="bugfix") # -> {params: {task, model, sessionTarget}}
cost = router.estimate_cost("design landing page")         # -> {tier, model, cost, currency}
```

---

## Input validation

IntentRouter validates all task strings before routing:

- **Empty/whitespace** -- rejected
- **Overly long** (>4000 chars) -- rejected
- **Prompt injection** -- patterns like "ignore previous instructions", "you are now a", "override safety filter" are rejected
- Validation runs both in the CLI and in `spawn_agent()`

---

## Tier detection

| Tier | Example keywords |
|------|------------------|
| **FAST** | check, get, list, show, status, monitor, fetch, simple |
| **REASONING** | prove, logic, analyze, derive, math, step by step |
| **CREATIVE** | creative, write, story, design, UI, UX, frontend, website (website projects -> Kimi k2.5 only) |
| **RESEARCH** | research, find, search, lookup, web, information |
| **CODE** | code, function, debug, fix, implement, refactor, test, React, JWT (not website builds) |
| **QUALITY** | complex, architecture, design, system, comprehensive |
| **VISION** | image, picture, photo, screenshot, visual |

- **Vision** has priority: if vision keywords are present, task is VISION regardless of other keywords.
- **Agentic** tasks (multi-step) are bumped to at least CODE.

---

## Changelog

### v1.8.0 (Identity fix + security hardening)

**Identity resolution:**
- Fixed name/slug/displayName across SKILL.md, _meta.json, config.json, README.md, and router.py to consistently use "IntentRouter"
- Renamed class from `FridayRouter` to `IntentRouter`
- Updated CLI description and all user-facing references
- Removed stale REVIEW-name-conformity.md (no longer applicable)

**Security hardening:**
- Added `validate_task_string()` function for input validation
- Added prompt-injection rejection (10 patterns covering common injection techniques)
- Added max task length enforcement (4000 chars)
- Validation runs in both CLI and `spawn_agent()` method
- Removed unused `math` import

**Config cleanup:**
- Removed redundant COMPLEX tier from routing_rules (was identical to QUALITY)
- COMPLEX keyword matches now map to QUALITY tier in classify_task

### v1.7.0 (Security-focused release)

- Removed gateway auth secret exposure
- Removed gateway management functionality
- Removed FACEPALM integration
- Clean separation of concerns

---

## Configuration

- **`config.json`** -- Model list and `routing_rules` per tier; `default_model` (e.g. `openrouter/google/gemini-2.5-flash`) for session default and orchestrator.
- Router loads `config.json` from the parent of `scripts/` (skill root).

---

## Related skills

- **[gateway-guard](https://clawhub.ai/skills/gateway-guard)** -- Gateway auth management (use separately if needed)
- **[FACEPALM](https://github.com/RuneweaverStudios/FACEPALM)** -- Intelligent troubleshooting (use separately if needed)
- **[what-just-happened](https://clawhub.ai/skills/what-just-happened)** -- Summarizes gateway restarts

---

## License / author

Austin / RuneweaverStudios. Part of the OpenClaw skills ecosystem.
