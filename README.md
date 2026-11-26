# agy-statusline

Single-line, zero-dependency Python statusline script for the Google Antigravity CLI (`agy`).

## Features

- **Format:** `<dir> | <model> [effort] | ctx: <used%> | 5hr: <rem%> | 7d: <rem%>`
- **Live Orchestrator model tracking:** Displays `orch/plan: <planner>` during planning/Q&A turns and `orch/exec: <executor>` during execution turns by reading the active session `transcript.jsonl` (supporting both `~/.gemini/antigravity-cli/brain/` and `~/.gemini/antigravity/brain/`).
- **Automatic quota pool selection:** Maps Gemini/Orchestrator models to `gemini-*` buckets and third-party models (`claude`, `sonnet`, `opus`, `haiku`, `gpt`, `openai`, `o1`/`o3`/`o4`, `codex`) to `3p-*` buckets, dynamically following the active Orchestrator sub-model.
- **Zero external dependencies:** Uses only the Python standard library.

## Requirements

- Python 3.10+

## Setup

1. Copy `statusline.py` to your config directory and make it executable:

   ```bash
   mkdir -p ~/.config/agy
   cp statusline.py ~/.config/agy/statusline.py
   chmod +x ~/.config/agy/statusline.py
   ```

2. Add the `statusLine` block to `~/.gemini/antigravity-cli/settings.json`:

   ```json
   {
     "statusLine": {
       "type": "command",
       "command": "~/.config/agy/statusline.py"
     }
   }
   ```

   Or configure it interactively from inside `agy`:

   ```text
   /statusline ~/.config/agy/statusline.py
   ```
