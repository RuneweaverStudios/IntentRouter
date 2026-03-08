#!/usr/bin/env python3
"""
IntentRouter | OpenClaw Skill — Task-to-LLM routing for OpenClaw
Version 1.8.0

Classifies tasks by intent and routes to the optimal model tier.
Includes input validation and prompt-injection rejection.

Fixed bugs from original intelligent-router:
- Simple indicators now properly invert (high match = SIMPLE, not complex)
- Agentic tasks properly bump to at least MEDIUM tier
- Code keywords actually detected
- Confidence scores vary appropriately

Features:
- Keyword-based routing for obvious matches
- Weighted scoring for nuanced classification
- Input validation (validate_task_string) with prompt-injection rejection
- OpenClaw integration for spawning sub-agents
"""

import argparse
import json
import os
import re
import sys
from pathlib import Path

# OpenClaw imports (if available)
try:
    import openclaw
    HAS_OPENCLAW = True
except ImportError:
    HAS_OPENCLAW = False


# --- Input Validation ---

# Patterns that indicate prompt-injection attempts
_INJECTION_PATTERNS = [
    re.compile(r'ignore\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)', re.IGNORECASE),
    re.compile(r'disregard\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)', re.IGNORECASE),
    re.compile(r'forget\s+(all\s+)?(previous|prior|above)\s+(instructions?|prompts?|rules?)', re.IGNORECASE),
    re.compile(r'you\s+are\s+now\s+(a|an|the)\b', re.IGNORECASE),
    re.compile(r'new\s+instructions?:\s', re.IGNORECASE),
    re.compile(r'system\s*:\s', re.IGNORECASE),
    re.compile(r'\bDAN\b.*\bjailbreak\b', re.IGNORECASE),
    re.compile(r'act\s+as\s+if\s+you\s+have\s+no\s+(restrictions?|rules?|limits?)', re.IGNORECASE),
    re.compile(r'override\s+(your\s+)?(safety|content|ethical)\s+(filter|policy|guidelines?)', re.IGNORECASE),
    re.compile(r'pretend\s+(that\s+)?(you|your)\s+(are|have)\s+no\s+(rules?|restrictions?)', re.IGNORECASE),
]

# Maximum allowed task length (characters)
MAX_TASK_LENGTH = 4000


def validate_task_string(task: str) -> tuple:
    """Validate a task string for safety.

    Returns (is_valid: bool, error_message: str | None).
    - Rejects empty or whitespace-only input
    - Rejects overly long input (> MAX_TASK_LENGTH chars)
    - Rejects prompt-injection patterns
    """
    if not task or not task.strip():
        return False, "Task string is empty or whitespace-only."

    if len(task) > MAX_TASK_LENGTH:
        return False, f"Task string exceeds maximum length ({MAX_TASK_LENGTH} chars)."

    for pattern in _INJECTION_PATTERNS:
        if pattern.search(task):
            return False, "Task string contains a prompt-injection pattern and was rejected."

    return True, None


# --- OpenClaw Config ---

def get_current_openclaw_config():
    """Read tools.exec.host and tools.exec.node from openclaw.json (no gateway auth)."""
    openclaw_home = os.environ.get("OPENCLAW_HOME") or os.path.expanduser("~/.openclaw")
    config_path = Path(openclaw_home) / "openclaw.json"
    if not config_path.exists():
        return None
    try:
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
    except (json.JSONDecodeError, OSError):
        return None
    exec_config = config.get("tools", {}).get("exec", {})
    return {
        "tools_exec_host": exec_config.get("host", "sandbox"),
        "tools_exec_node": exec_config.get("node"),
    }


class IntentRouter:
    """Intelligent model router with keyword-based classification and input validation."""

    # Simple indicators that suggest SIMPLE/Fast tasks (NOT inverted anymore)
    SIMPLE_KEYWORDS = [
        'check', 'get', 'fetch', 'list', 'show', 'display', 'status',
        'what is', 'how much', 'tell me', 'find', 'search', 'summarize',
        'monitor', 'watch', 'read', 'look', 'simple', 'quick', 'fast'
    ]

    # Complex indicators that suggest QUALITY/Code tasks
    COMPLEX_KEYWORDS = [
        'build', 'create', 'implement', 'architect', 'design', 'system',
        'comprehensive', 'thorough', 'complex', 'multi', 'full-stack',
        'authentication', 'authorization', 'database', 'api', 'service'
    ]

    # Code-related keywords
    CODE_KEYWORDS = [
        'code', 'function', 'class', 'method', 'debug', 'fix', 'bug',
        'refactor', 'lint', 'test', 'unit', 'integration', 'component',
        'module', 'package', 'library', 'framework', 'import', 'export',
        'react', 'vue', 'angular', 'node', 'python', 'javascript',
        'typescript', 'rust', 'go', 'java', 'api', 'endpoint'
    ]

    # Reasoning keywords
    REASONING_KEYWORDS = [
        'prove', 'theorem', 'proof', 'derive', 'logic', 'reason',
        'analyze', 'reasoning', 'step by step', 'why', 'how does',
        'explain', 'mathematical', 'induction', 'deduction'
    ]

    # Creative keywords
    CREATIVE_KEYWORDS = [
        'creative', 'write', 'story', 'poem', 'article', 'blog',
        'design', 'UI', 'UX', 'frontend', 'website', 'landing',
        'copy', 'narrative', 'brainstorm', 'idea', 'concept'
    ]

    # Research keywords
    RESEARCH_KEYWORDS = [
        'research', 'find', 'search', 'lookup', 'web', 'information',
        'fact', 'review', 'compare', 'vs', 'versus', 'difference',
        'summary of', 'what are', 'best', 'top', 'alternatives'
    ]

    # Agentic/action keywords (multi-step tasks)
    AGENTIC_KEYWORDS = [
        'run', 'test', 'fix', 'deploy', 'edit', 'build', 'create',
        'implement', 'execute', 'refactor', 'migrate', 'integrate',
        'setup', 'configure', 'install', 'compile', 'debug'
    ]

    def __init__(self, config_path=None):
        """Initialize router with config file."""
        if config_path is None:
            # Default to config.json in parent directory of script
            script_dir = Path(__file__).parent
            config_path = script_dir.parent / 'config.json'

        self.config_path = Path(config_path)
        self.config = self._load_config()

    def _load_config(self):
        """Load and parse configuration file."""
        if not self.config_path.exists():
            raise FileNotFoundError(f"Configuration file not found: {self.config_path}")

        with open(self.config_path, 'r') as f:
            return json.load(f)

    def _keyword_match(self, text, keywords):
        """Count keyword matches (case-insensitive)."""
        text_lower = text.lower()
        return sum(1 for kw in keywords if kw.lower() in text_lower)

    def classify_task(self, task_description, return_details=False):
        """
        Classify a task into a tier using keyword matching + scoring.

        Returns: FAST, REASONING, CREATIVE, RESEARCH, CODE, QUALITY, or VISION
        """
        text = task_description.lower()

        # First, check for exact keyword tier matches (highest priority)
        tier_scores = {}

        # Count matches for each tier
        tier_scores['FAST'] = self._keyword_match(task_description, self.SIMPLE_KEYWORDS)
        tier_scores['REASONING'] = self._keyword_match(task_description, self.REASONING_KEYWORDS)
        tier_scores['CREATIVE'] = self._keyword_match(task_description, self.CREATIVE_KEYWORDS)
        tier_scores['RESEARCH'] = self._keyword_match(task_description, self.RESEARCH_KEYWORDS)
        tier_scores['CODE'] = self._keyword_match(task_description, self.CODE_KEYWORDS)
        tier_scores['COMPLEX'] = self._keyword_match(task_description, self.COMPLEX_KEYWORDS)

        # Check for vision keywords (highest priority - if image/picture/photo/screenshot present, force VISION)
        vision_keywords = ['image', 'picture', 'photo', 'screenshot', 'visual', 'see', 'describe what']
        vision_matches = self._keyword_match(task_description, vision_keywords)
        tier_scores['VISION'] = vision_matches

        # If vision keywords present, this IS a vision task - override other classifications
        if vision_matches > 0:
            return {
                'tier': 'VISION',
                'confidence': min(vision_matches / 3.0, 1.0),
                'tier_scores': {'VISION': vision_matches},
                'is_agentic': False
            }

        # Agentic task detection - if multi-step, bump to at least CODE
        agentic_count = self._keyword_match(task_description, self.AGENTIC_KEYWORDS)
        multi_step_patterns = [
            r'\bfirst\b.*\bthen\b', r'\bstep\s+\d+', r'\d+\.\s+\w+',
            r'\bnext\b', r'\bafter\b', r'\bfinally\b', r',\s*then\b'
        ]
        is_multi_step = any(re.search(p, text) for p in multi_step_patterns)

        if agentic_count >= 2 or is_multi_step:
            # Multi-step task - ensure at least CODE tier
            tier_scores['CODE'] += 2
            if tier_scores['FAST'] > 0:
                tier_scores['FAST'] = 0  # Override FAST if agentic

        # Find best matching tier
        if max(tier_scores.values()) == 0:
            # No keywords matched - default to FAST
            best_tier = 'FAST'
        else:
            best_tier = max(tier_scores, key=tier_scores.get)

        # Website/frontend projects -> CREATIVE (Kimi k2.5), never CODE
        website_project_keywords = [
            'website', 'web site', 'landing page', 'landing', 'frontend',
            'community site', 'online community', 'build a site', 'new site'
        ]
        if self._keyword_match(task_description, website_project_keywords) > 0:
            best_tier = 'CREATIVE'

        # Map COMPLEX to QUALITY (COMPLEX tier removed from routing_rules)
        if best_tier == 'COMPLEX':
            if tier_scores['CODE'] > 0:
                best_tier = 'CODE'
            else:
                best_tier = 'QUALITY'

        # Special handling: if both COMPLEX and FAST matched, prefer CODE/QUALITY
        if tier_scores['COMPLEX'] > 0 and tier_scores['FAST'] > 0:
            if tier_scores['COMPLEX'] >= tier_scores['FAST']:
                best_tier = 'QUALITY' if tier_scores['COMPLEX'] >= 2 else 'CODE'

        # Calculate confidence based on match strength
        max_score = max(tier_scores.values())
        confidence = min(max_score / 5.0, 1.0)  # Cap at 1.0, normalize around 5 matches = 100%

        result = {
            'tier': best_tier,
            'confidence': round(confidence, 3),
            'tier_scores': {k: v for k, v in tier_scores.items() if v > 0},
            'is_agentic': agentic_count >= 2 or is_multi_step
        }

        if not return_details:
            return result['tier']

        return result

    def get_default_model(self):
        """Return the default model (Gemini 2.5 Flash). Used for session default and orchestrator."""
        default_id = self.config.get('default_model')
        if not default_id:
            # Fallback: QUALITY tier primary
            tier_rules = self.config.get('routing_rules', {}).get('QUALITY', {})
            default_id = tier_rules.get('primary')
        for m in self.config.get('models', []):
            if m['id'] == default_id:
                return m
        return None

    def recommend_model(self, task_description):
        """Classify task and recommend the best model."""
        classification = self.classify_task(task_description, return_details=True)
        tier = classification['tier']

        # Get routing rules for this tier
        routing_rules = self.config.get('routing_rules', {})
        tier_rules = routing_rules.get(tier, {})

        # Get primary model
        primary_id = tier_rules.get('primary')

        # Find model in config
        model = None
        for m in self.config.get('models', []):
            if m['id'] == primary_id:
                model = m
                break

        # Fallback
        fallback = None
        fallback_ids = tier_rules.get('fallback', [])
        if fallback_ids:
            for fb_id in fallback_ids:
                for m in self.config.get('models', []):
                    if m['id'] == fb_id:
                        fallback = m
                        break

        return {
            'tier': tier,
            'model': model,
            'fallback': fallback,
            'classification': classification,
            'reasoning': self._explain(tier, classification)
        }

    def _explain(self, tier, classification):
        """Provide reasoning for tier selection."""
        explanations = {
            'FAST': 'Simple, quick task - monitoring, checks, summaries',
            'REASONING': 'Logical analysis, math, step-by-step reasoning',
            'CREATIVE': 'Creative writing, design, frontend work',
            'RESEARCH': 'Information lookup, web search, fact-finding',
            'CODE': 'Code generation, debugging, implementation',
            'QUALITY': 'Complex, comprehensive, architectural work',
            'VISION': 'Image analysis, visual understanding'
        }

        explanation = explanations.get(tier, 'General task')

        if classification.get('is_agentic'):
            explanation += ' [Multi-step agentic task detected]'

        return explanation

    def estimate_cost(self, task_description):
        """Estimate cost for a task."""
        result = self.recommend_model(task_description)
        model = result['model']

        if not model:
            return {'error': 'No model found for tier'}

        # Rough token estimates
        token_estimate = {
            'FAST': {'in': 500, 'out': 200},
            'REASONING': {'in': 2000, 'out': 1500},
            'CREATIVE': {'in': 1500, 'out': 2000},
            'RESEARCH': {'in': 1000, 'out': 500},
            'CODE': {'in': 2000, 'out': 1500},
            'QUALITY': {'in': 5000, 'out': 3000},
            'VISION': {'in': 500, 'out': 500}
        }

        tokens = token_estimate.get(result['tier'], {'in': 500, 'out': 200})

        input_cost = (tokens['in'] / 1_000_000) * model['input_cost_per_m']
        output_cost = (tokens['out'] / 1_000_000) * model['output_cost_per_m']

        return {
            'tier': result['tier'],
            'model': model['alias'],
            'cost': round(input_cost + output_cost, 4),
            'currency': 'USD'
        }

    def spawn_agent(self, task, session_target='isolated', label=None, required_exec_host='sandbox', required_exec_node=None):
        """Spawn an OpenClaw sub-agent with the appropriate model.

        Validates the task string first. Optionally checks tools.exec host/node;
        on mismatch returns needs_config_patch (no exit).
        Always returns one dict: either params+recommendation or needs_config_patch+message+recommended_config_patch.
        """
        # Validate input before routing
        is_valid, error_msg = validate_task_string(task)
        if not is_valid:
            return {
                "error": True,
                "message": error_msg,
                "params": None,
            }

        current_config = get_current_openclaw_config()
        current_exec_host = current_config["tools_exec_host"] if current_config else "sandbox"
        current_exec_node = current_config["tools_exec_node"] if current_config else None

        if required_exec_host and current_exec_host != required_exec_host:
            msg = (
                f"Task requires exec host '{required_exec_host}' but current config is '{current_exec_host}'. "
                "Apply the recommended config patch (triggers gateway restart if host=node)."
                if required_exec_host == "node"
                else f"Temporarily set default exec host to '{required_exec_host}'."
            )
            patch = json.dumps({"tools": {"exec": {"host": required_exec_host}}})
            return {
                "needs_config_patch": True,
                "message": msg,
                "recommended_config_patch": patch,
                "params": None,
            }

        if required_exec_host == "node" and required_exec_node and current_exec_node != required_exec_node:
            msg = (
                f"Task requires exec node '{required_exec_node}' but current config is '{current_exec_node}'. "
                "Apply the recommended config patch (triggers gateway restart)."
            )
            patch = json.dumps({"tools": {"exec": {"host": "node", "node": required_exec_node}}})
            return {
                "needs_config_patch": True,
                "message": msg,
                "recommended_config_patch": patch,
                "params": None,
            }

        recommendation = self.recommend_model(task)
        model = recommendation["model"]
        if not model:
            raise ValueError(f"No model found for tier: {recommendation['tier']}")

        params = {
            "task": task,
            "model": model["id"],
            "sessionTarget": session_target,
        }
        if label:
            params["label"] = label

        return {
            "params": params,
            "recommendation": recommendation,
        }


def main():
    """CLI entry point."""
    parser = argparse.ArgumentParser(description="IntentRouter | OpenClaw Skill - Task-to-LLM routing for OpenClaw.")
    sub = parser.add_subparsers(dest="command", required=True)

    # Common args for classify, score, cost that require a task
    for cmd_name in ["classify", "score", "cost"]:
        p = sub.add_parser(cmd_name, help=f"{cmd_name.capitalize()} task")
        p.add_argument("task", type=str, nargs='+', help="The task description string")
        p.add_argument("--json", action="store_true", help="Output JSON report")

    # Default command
    p_default = sub.add_parser("default", help="Show session default model")
    p_default.add_argument("--json", action="store_true", help="Output JSON report")

    # Models command
    p_models = sub.add_parser("models", help="List all models")
    p_models.add_argument("--json", action="store_true", help="Output JSON report")

    # Spawn command (always exit 0; with --json always one JSON object; needs_config_patch does not exit(1))
    p_spawn = sub.add_parser("spawn", help="Show spawn params for OpenClaw (sessions_spawn)")
    p_spawn.add_argument("task", type=str, nargs='+', help="The task string for the sub-agent")
    p_spawn.add_argument("--json", action="store_true", help="Machine-readable output for sessions_spawn")
    p_spawn.add_argument("--required_exec_host", type=str, default="sandbox", help="Required exec host (sandbox or node)")
    p_spawn.add_argument("--required_exec_node", type=str, default=None, help="Required exec node ID or name if host=node")
    p_spawn.add_argument("--label", type=str, default=None, help="Optional label for the sub-agent session")

    args = parser.parse_args()

    router = IntentRouter()

    task_str = ' '.join(args.task) if 'task' in args and args.task else ""

    # Validate task input for commands that accept task strings
    if args.command in ('classify', 'score', 'cost', 'spawn') and task_str:
        is_valid, error_msg = validate_task_string(task_str)
        if not is_valid:
            if getattr(args, 'json', False):
                print(json.dumps({"error": True, "message": error_msg}))
            else:
                print(f"Error: {error_msg}", file=sys.stderr)
            sys.exit(0)  # Always exit 0 for stable orchestration

    if args.command == 'default':
        m = router.get_default_model()
        if not m:
            print("No default model configured (missing default_model or QUALITY primary in config)", file=sys.stderr)
            sys.exit(1)
        if args.json:
            print(json.dumps({"model": m}))
        else:
            print("Session default model (capable by default):\n")
            print(f"   {m['alias']} ({m['id']})")
            print(f"   Cost: ${m['input_cost_per_m']}/${m['output_cost_per_m']} per M")
            print(f"   Use for: {', '.join(m.get('use_for', []))}")
            print("\n   Simple tasks down-route to FAST tier (e.g. Gemini 2.5 Flash).")

    elif args.command == 'classify':
        result = router.recommend_model(task_str)
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Task: {task_str}")
            print(f"\nClassification: {result['tier']}")
            print(f"   Confidence: {result['classification']['confidence']:.1%}")
            print(f"   Reasoning: {result['reasoning']}")
            if result['model']:
                m = result['model']
                print(f"\nRecommended Model:")
                print(f"   {m['alias']} ({m['id']})")
                print(f"   Cost: ${m['input_cost_per_m']}/${m['output_cost_per_m']} per M")
                print(f"   Use for: {', '.join(m.get('use_for', []))}")
            if result['fallback']:
                fb = result['fallback']
                print(f"\nFallback: {fb['alias']} ({fb['id']})")

    elif args.command == 'score':
        result = router.classify_task(task_str, return_details=True)
        if args.json:
            print(json.dumps(result))
        else:
            print(f"Task: {task_str}")
            print(f"\nTier: {result['tier']}")
            print(f"   Confidence: {result['confidence']:.1%}")
            print(f"   Agentic: {'Yes' if result['is_agentic'] else 'No'}")

            print(f"\nTier Scores:")
            for tier, score in sorted(result['tier_scores'].items(), key=lambda x: x[1], reverse=True):
                bar = '#' * score
                print(f"   {tier:10} {bar} ({score})")

    elif args.command == 'cost':
        result = router.estimate_cost(task_str)
        if args.json:
            print(json.dumps(result))
        else:
            if 'error' in result:
                print(f"Error: {result['error']}", file=sys.stderr)
            else:
                print(f"Task: {task_str}")
                print(f"\nCost Estimate:")
                print(f"   Tier: {result['tier']}")
                print(f"   Model: {result['model']}")
                print(f"   Est. Cost: ${result['cost']} {result['currency']}")

    elif args.command == 'models':
        if args.json:
            print(json.dumps(router.config.get('models', [])))
        else:
            print("Configured Models:\n")
            for model in router.config.get('models', []):
                print(f"  {model['alias']:20} [{model['tier']:8}] {model['id']}")
                print(f"                         ${model['input_cost_per_m']}/${model['output_cost_per_m']}/M")

    elif args.command == 'spawn':
        if not task_str:
            print("Error: spawn requires a task string", file=sys.stderr)
            sys.exit(1)

        spawn_result = router.spawn_agent(
            task=task_str,
            label=args.label,
            required_exec_host=args.required_exec_host,
            required_exec_node=args.required_exec_node,
        )

        if spawn_result.get("error"):
            if args.json:
                print(json.dumps(spawn_result))
            else:
                print(f"Rejected: {spawn_result['message']}")
        elif spawn_result.get("needs_config_patch"):
            if args.json:
                print(json.dumps(spawn_result))
            else:
                print("Configuration required!\n")
                print(f"   {spawn_result['message']}\n")
                print(f"   Recommended patch: {spawn_result['recommended_config_patch']}")
                print("   Then retry spawn after gateway restarts if needed.")
        else:
            if args.json:
                out = {k: v for k, v in spawn_result["params"].items()}
                out["recommendation"] = spawn_result["recommendation"]
                print(json.dumps(out))
            else:
                print(f"Task: {task_str}")
                print(f"\nOpenClaw Spawn Params:")
                print(f"   model: {spawn_result['params']['model']}")
                print(f"   sessionTarget: {spawn_result['params']['sessionTarget']}")
                print(f"\nFull recommendation:")
                print(f"   Tier: {spawn_result['recommendation']['tier']}")
                print(f"   Model: {spawn_result['recommendation']['model']['alias']}")

    else:
        print(f"Unknown command: {args.command}", file=sys.stderr)
        sys.exit(1)


if __name__ == '__main__':
    main()
