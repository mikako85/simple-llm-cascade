# Simple LLM Cascade

**An autonomous AI developer assistant with multi-model failover cascades, interactive tool interception, and execution sandboxing.**

[![Python 3.12+](https://img.shields.io/badge/python-3.12+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Powered by LiteLLM](https://img.shields.io/badge/Router-LiteLLM-purple.svg)](https://github.com/BerriAI/litellm)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

https://github.com/user-attachments/assets/68fc51dd-5c76-4e80-99f7-9559e03c14b3

---

## Overview

**Simple LLM Cascade** is an interactive, terminal-native AI development assistant designed for autonomous coding, debugging, and terminal operations. Unlike typical AI wrappers, it connects directly to your workspace while providing **robust security guardrails**, **multi-model resilience**, and **zero-token-waste context pruning**.

If your primary model hits rate limits (HTTP 429), server downtime (HTTP 500), or context limits, Cascade **automatically transitions down a configurable fallback chain** (e.g., DeepSeek ➔ Gemini Flash ➔ Groq Llama) without interrupting your conversation.

---

## Key Highlights

- **Resilient Model Cascades**: Define primary routes and ordered fallback chains powered by LiteLLM Router.
- **Three Autonomy & Security Modes**: Choose between strict interactive review (`ASK`), isolated containerization (`SANDBOX`), or full host autonomy (`YOLO`).
- **Interactive Diff Inspection**: Real-time unified color diffs displayed before any file is created, modified, or overwritten.
- **Privilege Escalation Protection**: Command-line privilege escalation heuristics, sensitive path guards (blocking `.env`, `~/.ssh`, `~/.aws`), and Firejail sandbox isolation in `SANDBOX` mode. In `ASK` mode, actions require interactive human approval; in `YOLO` mode, bash operates with autonomous host permissions.
- **Built-in Web Scraping & Research**: Search DuckDuckGo and extract clean Markdown from JavaScript-heavy documentation via Crawl4AI (with auto-provisioned headless Chromium).
- **Smart Context Pruning**: Automatically truncates older tool executions to prevent token overflow while preserving recent outputs.
- **Multi-file Context Attachment**: Pre-load project files directly into model context using `/add` and inspect with `/files`.

---

## Execution Modes

Cascade operates under three distinct security and autonomy policies:

| Mode | Flag | Description | File Writes | Bash Execution | Sandbox Isolation |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **`ASK`** *(Default)* | `-a`, `--ask` | Recommended for day-to-day development. Agent operates on the host but requires human approval. | Interactive Unified Diff (`[y/N]`) | Interactive Prompt (`[y/N]`) | No |
| **`SANDBOX`** | `-s`, `--sandbox` | Linux-native isolation via **Firejail**. Root filesystem is read-only, network is disabled (`--net=none`), and writes are locked to workspace. | Restricted to workspace | Restricted to isolated jail | **Yes (Firejail)** |
| **`YOLO`** | `-y`, `--yolo` | Fully autonomous host execution. Commands and file writes execute immediately without prompts. | Autonomous | Autonomous | No |

> [!NOTE]
> When launched inside **WSL (Windows Subsystem for Linux)**, Cascade automatically detects that Firejail cannot run nested namespaces and gracefully switches to `ASK` mode with an informational warning.

---

## Available Tools & Capabilities

The agent automatically selects and chains appropriate tools to complete complex tasks:

| Tool | Purpose | Security Rules |
| :--- | :--- | :--- |
| `write_file` | Creates or completely overwrites a text document. Automatically creates parent directories. | Displays unified color diff in `ASK` mode. Writing to root `/`, `/etc`, `/sys`, or `.git` is strictly forbidden. |
| `read_text_document` | Reads UTF-8 source code, config files, or logs. | Protected by configurable size cap (`max_kb=100`). Binary files rejected. |
| `list_directory` | Explores project directories and folder structures. | Trailing slash indicators for folders. |
| `run_bash_command` | Executes builds, unit tests, linters, and git commands. | Blocked if privilege escalation (`sudo`, `su`) is detected. Wrapped in process-groups with strict timeouts (30s) and output caps. |
| `search_web` | Searches the web using DuckDuckGo (`ddgs`) for quick snippets and documentation links. | Read-only web request. |
| `fetch_url_markdown` | Downloads full web pages and extracts clean Markdown via Crawl4AI. | Automatically provisions headless Chromium if missing. Executes JS rendering. |
| `get_current_directory` | Resolves host/sandbox working directory context. | Read-only state inspection. |
| `get_system_time` | Provides host date and time for temporal reasoning. | Read-only state inspection. |

---

## Installation

### Option 1: Using `uv` (Recommended — Fast & Isolated)

No pre-installed Python required:
```bash
# 1. Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# 2. Install Cascade globally
uv tool install git+https://github.com/mikako85/simple-llm-cascade.git
```

### Option 2: Using `pipx`

```bash
pipx install git+https://github.com/mikako85/simple-llm-cascade.git
```

### Option 3: Development / From Source

If you want to contribute or modify the codebase:
```bash
git clone https://github.com/mikako85/simple-llm-cascade.git
cd simple-llm-cascade

# Set up an isolated venv and install in editable mode with uv
uv venv
source .venv/bin/activate
uv pip install -e .
```

---

## Quick Start

1. **Launch Cascade inside any repository or workspace folder:**
   ```bash
   cd ~/projects/my-app
   cascade
   ```

2. **First-Time Configuration:**
   On your very first run, Cascade detects that no configuration exists and launches the interactive **Config Wizard**:
   * Add one or more model deployments (e.g. `deepseek`, `gemini-lite`, `groq-llama`).
   * Enter your API keys (stored safely in `~/.simple-llm-cascade/.env`).
   * Choose your active default model.
   * Optionally link models into fallback chains.
   * Select **Save changes and exit**.

3. **Start Coding:**
   ```text
   Chat opened with deepseek. [Mode: ASK] Type /help for help

   You: Create a math utility module math_utils.py with factorial and test it
   AI: I will create the file and verify its implementation.

   [ASK MODE] Agent wants to write file: math_utils.py
     [NEW FILE] 'math_utils.py' (28 lines, 782 bytes)
     + """Mathematical utility functions."""
     + def factorial(n: int) -> int:
     +     ...
   Save changes to this file? [y/N]: y

   File math_utils.py successfully created (28 lines and 782 characters written)
   ```

---

## Slash Commands & Navigation

Inside the chat prompt, manage the agent state and workspace using slash commands:

### System & Models
* **`/help`** — Display the complete interactive command reference card.
* **`/models`** — Show a formatted status box with the active model, all configured deployments, and fallback chains.
* **`/mode [ask|yolo|sandbox]`** — Inspect the current execution mode or switch modes dynamically on the fly.
* **`/config`** — Open the interactive configuration wizard to add/remove models, change routes, or edit fallback sequences with instant hot-reload.
* **`/prompt`** — Open `SYSTEM_PROMPT.md` in your system editor (`$EDITOR`, `nano`, `vim`, or `vi`) to modify long-term agent guidelines.

### Workspace & File Context
* **`/add <path>`** — Read and attach a local file directly into the model conversation context (cached in-memory, no tool call needed).
* **`/drop <path>`** — Detach a previously attached file from the active context.
* **`/files`** — List all project files currently attached to the conversation context.

### Session Persistence
* **`/sessions`** — View the list of all saved conversation transcripts.
* **`/save [name]`** — Save the current dialogue history to a JSON Lines (`.jsonl`) file in `~/.simple-llm-cascade/memory/sessions/`.
* **`/load <name>`** — Restore and resume a previously saved dialogue session.
* **`/delete <name>`** — Delete an existing session transcript.
* **`exit`** or **`q`** — Safely exit the chat session.

---

## Configuration Architecture

Cascade utilizes a **single, centralized configuration architecture** stored in your user profile:
* **Models & Settings**: `~/.simple-llm-cascade/models.yaml`
* **API Credentials**: `~/.simple-llm-cascade/.env` (protected with `chmod 600`)
* **Memory & Sessions**: `~/.simple-llm-cascade/memory/`

### Sample `models.yaml`

```yaml
settings:
  default_route: deepseek
  temperature: 0.7
  max_tool_iterations: 30
  keep_recent_tool_outputs: 20
  tool_stub_preserve_chars: 1500
  execution_mode: ask

models:
  - model_name: deepseek
    litellm_model: deepseek/deepseek-flash
    api_key_env: DEEPSEEK_API_KEY

  - model_name: gemini-lite
    litellm_model: gemini/gemini-2.5-flash
    api_key_env: GEMINI_API_KEY

  - model_name: groq-llama
    litellm_model: groq/llama-3.3-70b-versatile
    api_key_env: GROQ_API_KEY

fallbacks:
  - primary: deepseek
    chain:
      - gemini-lite
      - groq-llama
```

---

## CLI Arguments

You can pass runtime overrides directly when launching the executable:

```bash
# Run in autonomous YOLO mode (no interactive confirmation prompts)
cascade --yolo
cascade -y

# Run in interactive ASK mode (unified diff review before writes)
cascade --ask
cascade -a

# Run inside isolated Firejail sandbox (native Linux only)
cascade --sandbox
cascade -s

# Explicit mode selection
cascade --mode yolo
cascade -m sandbox
```

---

## Context Management & Token Optimization

To prevent conversation context overflow during long autonomous sessions:
* **Tool Message Pruning**: Cascade automatically keeps the last `keep_recent_tool_outputs` (default: `20`) tool outputs intact. Older tool results are safely truncated to compact preview stubs (`tool_stub_preserve_chars: 1500`) while retaining standard API `tool_call_id` mapping.
* **Firejail Path Mapping**: In `SANDBOX` mode, host project paths are transparently mapped to the virtual sandbox root so paths copied by the LLM always resolve properly.

---

## License

This project is licensed under the **MIT License** — see the [LICENSE](LICENSE) file for details.