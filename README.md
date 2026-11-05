# Simple LLM Cascade

Interactive autonomous AI developer assistant operating directly in your environment with multi-model fallback cascades, local sandbox execution (Firejail), and tool interception.

## Features

- **Multi-Model Routing & Fallbacks**: Built on LiteLLM Router — automatically fall back to alternative models if the primary provider fails.
- **Execution Modes**:
  - `ask`: Interactive user confirmation for mutating actions (file writes, bash commands).
  - `yolo`: Autonomous host execution.
  - `sandbox`: Isolated execution using Firejail (on supported Linux systems).
- **Built-in Tooling**: Local file editing (`write_file`, `read_text_document`), bash runner, web search (`ddgs`), and page scraping (`crawl4ai`).
- **Interactive CLI**: Rich terminal UI with slash commands (`/config`, `/models`, `/mode`, `/prompt`, `/sessions`).

## Installation

Using `uv` (recommended):
```bash
uv tool install git+https://github.com/ваш-логин/simple-llm-cascade.git
```
or using pipx:
```bash 
pipx install git+https://github.com/ваш-логин/simple-llm-cascade.git
```

## Usage

Start the agent in any project workspace:

```bash
cascade
```

Type /help in the chat to see available commands.
