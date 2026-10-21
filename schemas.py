"""JSON schemas for the tools exposed to the language model.

Each entry follows the OpenAI function-calling format. The list ships with
every completion request, so the descriptions act as prompts: they tell the
model which tools exist, when a tool is worth calling and which arguments it
accepts.
"""

TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_directory",
            "description": (
                "Return the absolute path of the agent working directory. "
                "Use it before running commands that rely on relative paths, "
                "or when the task depends on where the project is located."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_time",
            "description": (
                "Return the current local date and time of the host machine. "
                "Use it when the answer depends on the current date or time, "
                "or on elapsed real time."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "read_text_document",
            "description": (
                "Read a UTF-8 text document from disk and return its full "
                "content. Use it to inspect source code, configuration files "
                "or logs. Binary files and files larger than max_kb are "
                "rejected."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Path to the text document, either absolute or "
                            "relative to the working directory."
                        ),
                    },
                    "max_kb": {
                        "type": "integer",
                        "description": (
                            "Maximum allowed file size in kilobytes. "
                            "Defaults to 100."
                        ),
                    },
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": (
                "Search the web through DuckDuckGo and return a numbered "
                "list of results with titles, URLs and short snippets. Use it "
                "to discover pages or to check facts; follow up with "
                "fetch_url_markdown to read a page in full."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query in natural language.",
                    },
                    "max_results": {
                        "type": "integer",
                        "description": (
                            "Maximum number of results to return. "
                            "Defaults to 5."
                        ),
                    },
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_bash_command",
            "description": (
                "Execute a bash command inside the isolated project sandbox "
                "(Firejail). The network is disabled and writes outside the "
                "project folder are blocked. Use it to run tests, linters, "
                "git or small scripts."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": (
                            "Bash command to execute, for example pytest, "
                            "git status or python script.py."
                        ),
                    },
                },
                "required": ["command"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_directory",
            "description": (
                "List files and subdirectories of the given directory. "
                "Directories are marked with a trailing slash. Use it to "
                "explore the project layout before reading files."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Directory path, absolute or relative. "
                            "Defaults to the current directory."
                        ),
                        "default": ".",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_url_markdown",
            "description": (
                "Download a web page, execute its JavaScript if needed and "
                "return the content as clean Markdown via Crawl4AI. Use it "
                "to read documentation, articles or issue threads in full."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Direct URL of the page to parse.",
                    },
                },
                "required": ["url"],
            },
        },
    },
]
