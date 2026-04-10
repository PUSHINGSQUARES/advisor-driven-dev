# Advisor-Driven Development

**Use Opus as the brain. Let cheap models do the work.**

A pattern for Claude Code that cuts API costs by 60-80% on multi-step tasks. Opus stays in the orchestrator seat (planning, decisions, review). Haiku, Sonnet, Gemini, Kimi, MiniMax, and local models (Gemma) handle the mechanical execution.

Built on two dispatch paths:
1. **Agent tool** (Claude models) — subagents with full file access
2. **ask.py** (any provider) — text-in/text-out CLI for code generation, research, video analysis

---

## The Problem

Running Claude Code on Opus is powerful but expensive. Most turns in a session are mechanical — reading files, writing boilerplate, simple edits. You're paying Opus rates for work that Haiku could handle.

Anthropic's [Advisor Tool](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/advisor-tool) (beta) solves this at the API level — a cheap executor model consults Opus for strategic guidance mid-generation. But it's API-only. You can't use it inside Claude Code sessions.

**This repo recreates that pattern inside Claude Code** using existing tools:
- Opus orchestrates from the main session
- Subagents on cheaper models do the file work
- A CLI tool (`ask.py`) routes to any provider for text generation
- The orchestrator reviews everything before it ships

## How It Works

```
You (Opus) ─── plan ──────────────────────────────────────── review
                 │                                              ▲
                 ├── Agent(haiku) → edit file A ────────────────┤
                 ├── Agent(haiku) → edit file B ────────────────┤
                 ├── ask.py -m kimi → generate util code ──────┤
                 ├── ask.py -m gemini --video → analyze clip ──┤
                 └── Agent(sonnet) → complex refactor ─────────┘
```

**Opus tokens go to:** planning, architecture, tradeoff decisions, reviewing output.
**Cheap model tokens go to:** file reads, edits, code generation, boilerplate, research.

## Setup

### 1. Install the CLI tool

Copy `ask.py` to your project:

```bash
cp ask.py your-project/tools/ask.py
```

### 2. Store API keys

The tool reads from macOS Keychain. Store your keys:

```bash
# Anthropic (required)
security add-generic-password -s "com.your-project.keys" -a "apiKey_anthropic" -w "sk-ant-..." -U

# Google Gemini (optional)
security add-generic-password -s "com.your-project.keys" -a "apiKey_gemini" -w "AI..." -U

# Moonshot/Kimi (optional)
security add-generic-password -s "com.your-project.keys" -a "apiKey_moonshot" -w "sk-..." -U

# MiniMax (optional)
security add-generic-password -s "com.your-project.keys" -a "apiKey_minimax" -w "..." -U
```

Or modify the `KEYCHAIN_SERVICE` and `KEYCHAIN_ACCOUNTS` in `ask.py` to match your own keychain setup.

**Not on macOS?** Replace the `get_key()` function with environment variable reads:

```python
def get_key(provider: str) -> str:
    env_map = {
        "anthropic": "ANTHROPIC_API_KEY",
        "moonshot": "MOONSHOT_API_KEY",
        "google": "GEMINI_API_KEY",
        "minimax": "MINIMAX_API_KEY",
    }
    key = os.environ.get(env_map.get(provider, ""))
    if not key:
        print(f"Missing env var for {provider}", file=sys.stderr)
        sys.exit(1)
    return key
```

### 3. Set up local models (optional, free)

```bash
# Install Ollama
brew install ollama
brew services start ollama

# Pull Gemma 4 (26B, ~10GB)
ollama pull gemma4

# Pull Gemma 3 (4B, ~3GB) for fast lightweight tasks
ollama pull gemma3:4b
```

### 4. Add to your CLAUDE.md

Paste the routing instructions into your project's `CLAUDE.md` so every Claude Code session knows the pattern. See [claude-md-snippet.md](claude-md-snippet.md) for a ready-to-paste block.

### 5. Add the slash command

Copy `advisor.md` to `.claude/commands/advisor.md` in your project. This gives you `/advisor` as a slash command for structured multi-task execution.

## Usage

### ask.py — Multi-provider CLI

```bash
# Anthropic models
python3 tools/ask.py -m haiku "Simple question"
python3 tools/ask.py -m sonnet "Moderate complexity task"

# Kimi (Moonshot) — cheap, 128k context
python3 tools/ask.py -m kimi "Quick code generation task"
python3 tools/ask.py -m kimi-think "Complex reasoning problem"
python3 tools/ask.py -m kimi-swarm "Research task needing parallel decomposition"

# Gemini — strong coder, video analysis
python3 tools/ask.py -m gemini "Generate a React component for..."
python3 tools/ask.py -m gemini --video clip.mp4 "Review this edit for pacing"

# MiniMax — cheap, multilingual
python3 tools/ask.py -m minimax "Simple utility function"

# Local (Ollama) — free, private, offline
python3 tools/ask.py -m gemma "Draft some copy for..."
python3 tools/ask.py -m gemma-small "Reformat this JSON"

# With system prompt
python3 tools/ask.py -m kimi -s "You are a Python expert" "Write a decorator for..."

# Pipe input
cat large_file.txt | python3 tools/ask.py -m kimi --stdin
```

### Agent tool — Claude subagents with file access

Inside a Claude Code session, dispatch work to cheaper models:

```
Agent({
  description: "Add input validation to form.tsx",
  model: "haiku",
  prompt: "Add email validation to the signup form at src/components/form.tsx. Use zod schema validation. The form currently has name and email fields with no validation."
})
```

### /advisor — Structured multi-task execution

```
/advisor Add a password reset flow to the auth system
```

Opus breaks it down, dispatches each task to the cheapest capable model, handles escalations, reviews everything.

## Model Selection Guide

### For code

| Complexity | Model | Path | Why |
|-----------|-------|------|-----|
| Complex (multi-file, refactors) | `sonnet` | Agent tool | Strong coder, file access |
| Complex (second opinion) | `gemini` | ask.py | Different perspective |
| Simple (single file, clear spec) | `haiku` | Agent tool | Cheap, file access |
| Simple (single function, util) | `kimi` / `minimax` | ask.py | Cheaper than Haiku |
| Simple (no cost needed) | `gemma` | ask.py (local) | Free |

### For non-code

| Task | Model | Why |
|------|-------|-----|
| Multi-step research | `kimi-swarm` | 100 parallel sub-agents |
| Deep analysis | `kimi-think` | Extended reasoning |
| Long documents | `kimi` | 128k context |
| Video analysis | `gemini --video` | Native video understanding |
| Drafts, copy | `gemma` | Free, local |
| Bulk generation | `gemma` | No API cost at scale |

## Kimi Modes

Kimi K2.5 has four operating modes, all on the same model:

| Mode | Flag | What it does |
|------|------|-------------|
| Instant | `kimi` | Standard fast inference |
| Thinking | `kimi-think` | Extended reasoning (like Claude's thinking) |
| Agent | `kimi-agent` | Single agentic loop with tool use |
| Swarm | `kimi-swarm` | Spawns up to 100 parallel sub-agents, 1500 tool calls |

Agent Swarm is automatic — you give it a complex task and the model decomposes and parallelizes it internally. No framework needed.

## Video Analysis with Gemini

Gemini natively accepts video files. No frame extraction, no local vision model — it sees the actual video with temporal understanding.

```bash
# Scene descriptions
python3 tools/ask.py -m gemini --video footage.mp4 \
  "Describe each scene chronologically, noting camera movement, subjects, and mood"

# Edit review
python3 tools/ask.py -m gemini --video rough_cut.mp4 \
  "Review this edit for pacing. Note cuts that feel too fast or too slow."

# Shot list
python3 tools/ask.py -m gemini --video clip.mov \
  "Create a timestamped shot list with scene descriptions and shot types"

# Social content review
python3 tools/ask.py -m gemini --video reel.mp4 \
  "Is this suitable for Instagram? Check visual quality, pacing, hook in first 3s"
```

The video is uploaded to Gemini's Files API, analyzed, then deleted. Works with .mp4, .mov, .mkv, .avi, .webm.

## Anthropic's Advisor Tool (API-level)

If you're building your own agents via the API (not Claude Code), you can use Anthropic's actual [Advisor Tool](https://docs.anthropic.com/en/docs/agents-and-tools/tool-use/advisor-tool) (beta). This is a server-side tool where the executor model consults Opus mid-generation — all within a single API request.

```python
import anthropic

client = anthropic.Anthropic()

response = client.beta.messages.create(
    model="claude-sonnet-4-6",
    max_tokens=8192,
    betas=["advisor-tool-2026-03-01"],
    tools=[
        {
            "type": "advisor_20260301",
            "name": "advisor",
            "model": "claude-opus-4-6",
            "max_uses": 2,
        }
    ],
    messages=[
        {"role": "user", "content": "Build a concurrent worker pool in Go with graceful shutdown."}
    ],
)
```

The executor (Sonnet) decides when to consult the advisor (Opus). The advisor sees the full transcript and returns strategic guidance. One API request, no extra round trips.

### Valid model pairs

| Executor | Advisor |
|----------|---------|
| Haiku 4.5 | Opus 4.6 |
| Sonnet 4.6 | Opus 4.6 |
| Opus 4.6 | Opus 4.6 |

## Cost Impact

Rough example — a 10-task coding session:

| Approach | Token distribution | Relative cost |
|----------|-------------------|---------------|
| All Opus | 100% Opus | 1x |
| Advisor pattern | 20% Opus (plan + review) + 60% Haiku + 20% Sonnet | ~0.25x |
| With local models | 20% Opus + 40% Haiku + 20% Sonnet + 20% Gemma (free) | ~0.20x |

The exact savings depend on your workload, but the principle holds: most turns in a coding session are mechanical. Pay for intelligence only when you need it.

## Requirements

- macOS (for Keychain — see setup for env var alternative)
- Python 3.10+
- Claude Code CLI
- API keys for providers you want to use
- Ollama (optional, for local models)

## Files

| File | Purpose |
|------|---------|
| `ask.py` | Multi-provider LLM CLI |
| `advisor.md` | Slash command for `/advisor` |
| `claude-md-snippet.md` | Ready-to-paste CLAUDE.md routing instructions |
| `README.md` | This file |

## License

MIT
