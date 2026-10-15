TOOLS_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "get_current_directory",
            "description": "Возвращает текущий каталог",
            "parameters": {
                "type": "object", 
                "properties": {}, 
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_system_time",
            "description": "Возвращает текущее системное время",
            "parameters": {
                "type": "object", 
                "properties": {}, 
                "required": []
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "read_text_document",
            "description": "Возвращает содержимое текстового документа по указанному пути",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": "Путь к текстовому документу"
                    },
                    "max_kb": {
                        "type": "integer",
                        "description": "Максимальный размер файла в КБ (по умолчанию 100)"
                    }
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_web",
            "description": "Поиск информации в интернете",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string", 
                        "description": "Запрос для поиска"
                    },
                    "max_results": {
                        "type": "integer", 
                        "description": "Максимальное количество результатов"
                    }
                },
                "required": ["query"]
            }
        }
    },
    {
    "type": "function",
    "function": {
        "name": "run_bash_command",
        "description": "Выполняет консольную bash-команду в изолированной песочнице проекта. Сеть отключена, запись за пределами папки проекта заблокирована.",
        "parameters": {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "Bash-команда для выполнения (например, pytest, git status, python script.py)"
                }
            },
            "required": ["command"]
        }
    }
},
{
    "type": "function",
    "function": {
        "name": "list_directory",
        "description": "Возвращает содержимое указанной директории (список файлов и подпапок).",
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Путь к директории (относительный или абсолютный). По умолчанию текущая папка ('.')",
                    "default": "."
                }
            },
            "required": []
        }
    }
},
{
        "type": "function",
        "function": {
            "name": "fetch_url_markdown",
            "description": "Загружает веб-страницу по URL, выполняет JavaScript (если требуется) и возвращает её содержимое в формате чистого Markdown с помощью Crawl4AI.",
            "parameters": {
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "Прямой URL веб-страницы для парсинга"
                    }
                },
                "required": ["url"]
            }
        }
    },
    
]