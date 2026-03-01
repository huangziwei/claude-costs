# claude-code-config

My custom Claude Code enhancements.

## Install

```bash
curl -fsSL https://raw.githubusercontent.com/huangziwei/claude-code-config/main/install.sh | bash
```

Or clone and run locally:

```bash
git clone https://github.com/huangziwei/claude-code-config.git
bash claude-code-config/install.sh
```

The installer is idempotent — safe to run multiple times. It merges into your existing `~/.claude/settings.json` without overwriting other settings.

## What's included

### Status line

Shows model, context remaining, session cost, working directory, and git branch:

```
Opus 4.6 · context: 77% left · $1.26 this session · ~/projects/myapp (main)
```

### Session cost logger

A `SessionEnd` hook that parses the session transcript and appends token usage and estimated API cost to `~/.claude/session-costs.csv`:

```csv
timestamp,session_id,project,model,input_tokens,output_tokens,cache_read_tokens,cache_create_5m_tokens,cache_create_1h_tokens,total_tokens,cost_usd,turns,reason
2026-03-01T12:45:41Z,abc123,myapp,claude-opus-4-6,1200,8500,45000,0,3000,57700,0.2481,12,other
```

Costs are estimated using current API pricing (not billed to Max/Pro subscribers, but useful for tracking usage).

## Requirements

- `jq` (used by the status line script)
- `python3` (used by the cost logger)
- `git` (optional, for branch display)

## Files

| Installed to | Purpose |
|---|---|
| `~/.claude/statusline-command.sh` | Status line script |
| `~/.claude/hooks/session-cost-logger.py` | Session cost logger |
| `~/.claude/settings.json` | Merged (not overwritten) |
| `~/.claude/session-costs.csv` | Accumulated session costs (created on first session end) |
