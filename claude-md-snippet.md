# CLAUDE.md Snippet — Advisor-Driven Execution

Paste this into your project's `CLAUDE.md` to enable advisor-driven development by default in every Claude Code session.

---

## Advisor-Driven Execution

**Default operating mode for multi-step work.** You (Opus) are the advisor — you plan, make decisions, and review. Subagents on cheaper models do the mechanical work.

### Routing Table

| Work type | Model | Path | Notes |
|-----------|-------|------|-------|
| **You (Opus) — never delegate** | | | |
| Planning, architecture, task breakdown | Opus | — | |
| Strategic decisions, tradeoff calls | Opus | — | |
| Review, spot-checks, final verification | Opus | — | |
| Tiny edits (< 5 lines, obvious) | Opus | — | Dispatch overhead > savings |
| **Coding — main tasks (needs reasoning + file access)** | | | |
| Complex multi-file code, architecture, refactors | `sonnet` | Agent tool | Strongest Claude coder below Opus |
| Complex code needing different perspective | `gemini` | `ask.py` -> you paste | Strong at structured code, different strengths to Anthropic |
| **Coding — simple tasks (mechanical, clear spec)** | | | |
| Isolated file edits, boilerplate, clear specs | `haiku` | Agent tool | Cheapest with file access |
| Simple code generation (single function, util, config) | `kimi` / `minimax` | `ask.py` -> you paste | Cheaper than Haiku, good enough for simple code |
| Simple code you'll review and place yourself | `gemma` | `ask.py` (Ollama) | Free, local, no API cost |
| **Research & analysis** | | | |
| Complex multi-step research, parallel decomposition | `kimi-swarm` | `ask.py` | Up to 100 sub-agents |
| Extended reasoning, deep analysis | `kimi-think` | `ask.py` | |
| Long-context processing (large docs, transcripts) | `kimi` | `ask.py` | 128k context |
| Second opinion from different model family | `gemini` | `ask.py` | |
| **Media & content** | | | |
| Video analysis (scenes, pacing, edit review) | `gemini` | `ask.py --video` | Native video understanding |
| Drafts, copy, captions, reformatting | `gemma` / `kimi` / `minimax` | `ask.py` | Cheapest option that fits |
| Bulk generation (many items, cost matters) | `gemma` | `ask.py` (Ollama) | Free, unlimited |

### Dispatch Paths

- **Agent tool** `Agent({ model: "haiku"/"sonnet", ... })` — Claude subagents with full tool access (read/edit/grep/test). Use when the task needs to touch files.
- **ask.py** `python3 tools/ask.py -m <model> "prompt"` — any provider, text-in/text-out. Use when you need code generated that you'll place into files yourself, or for non-code tasks.

### How It Works

Break work into tasks. For each: pick the cheapest model that can handle it, pick the right dispatch path based on whether it needs file access. If a subagent reports `NEEDS_GUIDANCE` or `BLOCKED`, provide strategic direction and re-dispatch. Never delegate planning or review.

**When to skip this:** Single small edits, exploration/debugging (investigate first, dispatch after), tightly coupled work where every file depends on every other file.
