---
name: intent-router
displayName: IntentRouter | OpenClaw Skill
description: Intelligent LLM routing for OpenClaw. Classifies tasks by intent and routes to the optimal model tier (code, creative, research, reasoning, vision) with prompt-injection protection.
version: 1.8.0
---

# IntentRouter | OpenClaw Skill

**Intelligent LLM routing for OpenClaw.** Classifies tasks by intent and routes each to the optimal model, with input validation and prompt-injection protection.

**v1.8.0 — Identity fix + security hardening.** Resolved naming to IntentRouter. Added input validation (`validate_task_string`) and prompt-injection rejection. Removed gateway auth secret exposure.

IntentRouter analyzes your tasks and directs them to the best LLM -- MiniMax 2.5 for code, Kimi k2.5 for creative, Grok Fast for research, GLM-5 for reasoning, GPT-4o for vision. Eliminate guesswork; route with purpose.

**Requirements:** **OpenRouter** -- All model IDs use the `openrouter/...` prefix. Configure OpenClaw with an OpenRouter API key so one auth profile covers every tier.

**Config access:** This skill reads its own `config.json` for models and routing rules, and reads `openclaw.json` only for `tools.exec.host` and `tools.exec.node` (to detect exec mismatch and recommend a config patch). It does NOT access gateway tokens/passwords. Router output contains: `task`, `model`, `sessionTarget`, optional `label`; or when exec mismatch, `needs_config_patch`, `message`, `recommended_config_patch` -- no secrets or credentials.

**Critical stable orchestration:** The router always exits 0 and with `--json` prints one JSON object. If exec host/node mismatch is detected, the JSON includes `needs_config_patch`, `message`, and `recommended_config_patch` (and no `params`). When so, do **not** call `sessions_spawn`; report the message and patch to the user (e.g. apply patch or run gateway-guard). When `needs_config_patch` is absent or false, call `sessions_spawn` with `task`, `model`, `sessionTarget` (and `label` if present).

**Default / orchestrator model:** Gemini 2.5 Flash (`openrouter/google/gemini-2.5-flash`) -- fast, cheap, reliable at tool-calling. The router delegates tasks to tier-specific sub-agents (Kimi for creative, MiniMax 2.5 for code, etc.).

## Orchestrator flow (mandatory for task requests)

When you are the **main agent** (Gemini 2.5 Flash), you **classify** the user request by running the router; you do **not** perform the task yourself -- a sub-agent does. For any **task** (code, research, write, create, design, poem, story, fix, build, etc.), you must **delegate**.

**Steps (all three required):**

1. **Run IntentRouter** to classify and get spawn params:
   ```bash
   python3 workspace/skills/intent-router/scripts/router.py spawn --json "<user message>"
   ```
   Example output: `{"task":"write a poem about Mai","model":"openrouter/moonshotai/kimi-k2.5","sessionTarget":"isolated"}`. The router may instead return `{"needs_config_patch":true,"message":"...","recommended_config_patch":"..."}` when exec host/node mismatch is detected.

2. **Parse the JSON.** If `needs_config_patch` is true, do **not** call `sessions_spawn`. Report the `message` and `recommended_config_patch` to the user (e.g. "Exec config mismatch. Apply this patch or run gateway-guard.") and stop. Otherwise **immediately call `sessions_spawn`** with the router's output. Use the **exact `model`** from the JSON. Example:
   ```
   sessions_spawn(task="write a poem about Mai", model="openrouter/moonshotai/kimi-k2.5", sessionTarget="isolated")
   ```
   Do **not** change the `model` value. If the router said `openrouter/moonshotai/kimi-k2.5`, pass exactly that.

3. **Forward the sub-agent's reply** to the user. That reply IS the task output. Say "Using: Kimi k2.5" (the model that actually ran). Never say "Using: Claude Sonnet 4" or any model that didn't run. **Output hygiene:** If the sub-agent result contains internal text ("A subagent task ... completed", "Findings:", "Stats:", "sessionKey", "Summarize this naturally"), strip that block and show only the final user-facing content to the user.

**If `sessions_spawn` returns an error** (e.g. `device_token_mismatch`): tell the user delegation failed and suggest checking gateway status or using the `gateway-guard` skill. Do **not** do the task yourself.

**Hard-stop rule:** If `sessions_spawn` fails or is skipped, return only the delegation error and next-step fix. Do not write the requested output directly.

**No-classify execution rule:** For real user tasks, do not execute via `classify`. `classify` is diagnostics only. Execution must use `spawn --json` -> `sessions_spawn`.

**Label gate:** Only print `Using: <model>` after successful spawn. If no successful spawn, do not print a `Using:` label.

**Output hygiene:** Never return internal orchestration metadata to the user (no session keys/IDs, transcript paths, runtime/token stats, or internal "summarize this" instructions). Forward only clean user-facing content.

**Exception:** Meta-questions ("what model are you?", "how does routing work?") you answer yourself.

**Security note:** This skill does NOT expose gateway auth secrets (tokens/passwords) in its output. Gateway management functionality has been removed. Use the separate `gateway-guard` skill if gateway auth management is needed. All task inputs are validated against prompt-injection patterns before routing.

## Model Selection

| Use Case | Primary (OpenRouter) | Fallback |
|----------|---------------------|----------|
| **Default / orchestrator** | Gemini 2.5 Flash | -- |
| **Fast/cheap** | Gemini 2.5 Flash | Gemini 1.5 Flash, Haiku |
| **Reasoning** | GLM-5 | Minimax 2.5 |
| **Creative/Frontend** | Kimi k2.5 | -- |
| **Research** | Grok Fast | -- |
| **Code/Engineering** | MiniMax 2.5 | Qwen2.5-Coder |
| **Quality/Complex** | GLM 4.7 Flash | GLM 4.7, Sonnet 4, GPT-4o |
| **Vision/Images** | GPT-4o | -- |

All model IDs use `openrouter/` prefix (e.g. `openrouter/moonshotai/kimi-k2.5`).

## Usage

### CLI

```bash
python scripts/router.py default                          # Show default model
python scripts/router.py classify "fix lint errors"        # Classify -> tier + model
python scripts/router.py spawn --json "write a poem"       # JSON for sessions_spawn
python scripts/router.py models                            # List all models
```

**Note:** Gateway auth management is not included. Use `gateway-guard` skill separately if needed.

### sessions_spawn examples

**Creative task (poem):**
```
router output: {"task":"write a poem","model":"openrouter/moonshotai/kimi-k2.5","sessionTarget":"isolated"}
-> sessions_spawn(task="write a poem", model="openrouter/moonshotai/kimi-k2.5", sessionTarget="isolated")
```

**Code task (bug fix):**
```
router output: {"task":"fix the login bug","model":"openrouter/minimax/minimax-m2.5","sessionTarget":"isolated"}
-> sessions_spawn(task="fix the login bug", model="openrouter/minimax/minimax-m2.5", sessionTarget="isolated")
```

**Research task:**
```
router output: {"task":"research best LLMs","model":"openrouter/x-ai/grok-4.1-fast","sessionTarget":"isolated"}
-> sessions_spawn(task="research best LLMs", model="openrouter/x-ai/grok-4.1-fast", sessionTarget="isolated")
```

## Tier Detection

- **FAST**: check, get, list, show, status, monitor, fetch, simple
- **REASONING**: prove, logic, analyze, derive, math, step by step
- **CREATIVE**: creative, write, story, design, UI, UX, frontend, website (website/frontend/landing projects -> Kimi k2.5 only; do not use CODE tier)
- **RESEARCH**: research, find, search, lookup, web, information
- **CODE**: code, function, debug, fix, implement, refactor, test, React, JWT (code/API only; not website builds)
- **QUALITY**: complex, architecture, design, system, comprehensive
- **VISION**: image, picture, photo, screenshot, visual

## What Changed from Original

| Bug | Fix |
|-----|-----|
| Simple indicators inverted (high match = complex) | Now correctly: high simple keyword match = FAST tier |
| Agentic tasks not bumping tier | Multi-step tasks now properly bump to CODE tier |
| Vision tasks misclassified | Vision keywords now take priority over other classifications |
| Code keywords not detected | Added React, JWT, API, and other common code terms |
| Confidence always low | Now varies appropriately based on keyword match strength |
