[<-- README.md](README.md) | [<-- USER_MANUAL.md](USER_MANUAL.md) | [Next: CONTRIBUTING.md -->](CONTRIBUTING.md)
---
# Project Smol Agent - Technical & Developer Documentation

## 1. High-Level Architecture

Project Smol Agent is a Python application built on a decoupled, multi-threaded architecture designed to separate UI responsiveness from backend logic. This separation is fundamental to its operation and is achieved through two main threads and two corresponding queues.

-   **The GUI Thread**: Managed by Tkinter's `mainloop()`. It is solely responsible for rendering the UI, capturing user input (clicks, key presses), and displaying data. It performs no blocking operations and has no direct knowledge of the LLM, file system logic, or agent state.

-   **The ChatManager Thread**: This is the application's core. It runs in a dedicated `threading.Thread` and manages all backend logic: agent state, prompt construction, LLM API calls, file I/O, memory management, and TTS processing. It is designed to be entirely headless.

-   **Communication Queues**: The two threads communicate exclusively through two `queue.Queue` instances, which are thread-safe by nature. This prevents race conditions and ensures a clean, message-passing architecture.
    -   `ui_to_manager_q`: Carries commands from the GUI to the ChatManager (e.g., user sent a message, save settings, hard reset).
    -   `manager_to_ui_q`: Carries updates and data from the ChatManager to the GUI (e.g., new agent message, update a log pane, update status bar).

### Data Flow of a Single User-Initiated Turn:

1.  User types a message in the `gui.py` `Entry` widget and hits Enter.
2.  The `send_message` method in `App` is called. It creates a dictionary: `{"type": "user_message", "payload": "..."}`.
3.  This dictionary is placed onto the `ui_to_manager_q`.
4.  The `ChatManager` thread, in its `_process_incoming_commands` loop, gets the message from the queue.
5.  The `_should_trigger_turn` method now returns `True`.
6.  The `_execute_turn` method is called.
7.  `_construct_prompt_from_state` assembles the full context from memory, chat history, and the new user message.
8.  `ChatManager` calls `self.llm_handler.generate_response` with the prompt.
9.  `LLMHandler` makes the HTTPS request to the Google Gemini API.
10. `LLMHandler` receives the response and formats it into a standardized dictionary.
11. `ChatManager` receives this dictionary. It parses the response, extracts commands, and updates its internal state (e.g., `self.current_self_prompts`).
12. For every piece of information that needs to be displayed, `ChatManager` creates a dictionary (e.g., `{"type": "new_message", ...}`, `{"type": "update_memory_log", ...}`) and puts it on the `manager_to_ui_q`.
13. The `App` class, in its `process_incoming` loop (scheduled with `self.after`), gets these messages and calls the appropriate rendering methods (`add_chat_message`, `update_memory_log`, etc.) to update the UI.

---

## 2. Core Components: File-by-File Breakdown

### `main.py` - The Orchestrator

This script is the application's entry point. Its responsibilities are limited to setup, instantiation, and teardown.

-   **`load_or_create_config()`**: This is the first critical step. It loads `config.json` or, if it's missing or corrupt, creates a new one from the hardcoded `get_default_config()`. It performs a "deep update" to ensure that new keys added in an update are merged into existing user configs, preserving their settings while enabling new features.
-   **`setup_project_directories_and_files()`**: Ensures the `/prompts/`, `/memory/`, and `/terminal/` directories exist. It also creates placeholder prompt files if they are missing, preventing crashes on a fresh clone.
-   **`main()`**:
    1.  Loads the config.
    2.  Sets up directories.
    3.  Creates the two `queue.Queue` instances.
    4.  Instantiates `ChatManager`, passing it the queues and config. **Note**: The `LLMHandler` is instantiated *inside* the `ChatManager`, not here.
    5.  Instantiates the `App` (GUI), passing it the same queues and config.
    6.  Creates and starts the `ChatManagerThread`. It is crucial that this is a `daemon=True` thread so it will exit when the main GUI thread exits.
    7.  Defines the `on_closing` protocol, which ensures settings are saved and the manager thread is gracefully stopped before the application closes.
    8.  Starts the Tkinter `mainloop()`.

### `llm_handler.py` - The API Abstraction Layer

This class is a wrapper around the `google-generativeai` library. Its purpose is to completely isolate all API-specific code from the rest of the application. This makes it trivial to swap out the LLM provider in the future.

-   **`LLMHandler.__init__(self, api_key)`**: Takes the API key and immediately calls `update_api_key`.
-   **`update_api_key(self, api_key)`**:
    -   Configures the `genai` library with the key.
    -   Instantiates the `genai.GenerativeModel`.
    -   **Crucially**, it performs a lightweight validation call (`self.model.count_tokens("test")`) to immediately check if the key is valid and has permissions for the model.
    -   Sets the `self.api_key_is_valid` boolean flag, which `ChatManager` uses to determine if it can proceed with a turn.
-   **`generate_response(self, prompt, params)`**:
    -   This is the single point of contact for the `ChatManager`.
    -   It translates the application's generic parameter names (`temperature`, `top_k`, `top_p`) into a `genai.GenerationConfig` object.
    -   It sets the `safety_settings` to `BLOCK_NONE`. This is a design choice to give the user maximum control via prompting and to prevent the API from silently refusing to respond to borderline content. The agent will instead receive a clear "prompt-blocked" message it can reason about.
    -   It calls `self.model.generate_content()`.
    -   **Compatibility Layer**: After receiving the `response` object, it manually reconstructs a dictionary that mimics the output format of other common LLM libraries: `{"choices": [{"text": ...}], "usage": ...}`. This makes the `LLMHandler` a drop-in replacement for other potential handlers.
    -   It handles specific errors, such as `PermissionDenied`, and updates its own `api_key_is_valid` state if an API call fails due to authentication.

### `chat_manager.py` - The Brains of the Operation

This is the most complex and important component. It is a long-running object that holds the agent's entire state in memory.

-   **`__init__`**:
    -   Initializes dozens of state variables from the loaded `config` dictionary (`self.agent_name`, `self.llm_params`, `self.memory_capacities`, etc.).
    -   Loads session state (`has_history`, `chat_history_on_load`, `last_self_prompt`) to resume a previous conversation. If no history exists, it sets the `self.current_self_prompts` to the `initial_self_prompt`.
    -   Initializes the `deque` for `recent_chat_log` for efficient, fixed-size logging.
    -   Calls `_update_dynamic_patterns()` to compile regex patterns using the agent's name. This is vital for parsing the agent's output correctly.

-   **The Main Loop (`run`)**:
    -   This is an infinite loop that breaks only when `self.is_running` is cleared.
    -   It first calls `_process_incoming_commands()` to react to any user actions.
    -   Then, `_should_trigger_turn()` checks if conditions are met for the agent to act (user message pending, auto-turn timer elapsed, etc.).
    -   If a turn is triggered, it calls the master `_execute_turn()` method.
    -   It sleeps for a short duration to prevent high CPU usage.

-   **State and Prompting (`_execute_turn` and `_construct_prompt_from_state`)**:
    -   `_construct_prompt_from_state` is the heart of the agent's "perception". It meticulously assembles the `Full Context` by concatenating strings in a specific order: System Prompt -> Memories (LTM, MTM, STM) -> Chat History -> File List -> Input Injector -> Time/Status -> Current Self-Prompt -> File Read Content -> User Message -> Assistant Response Start. This precise order is critical to how the LLM prioritizes information.
    -   `_execute_turn` sends this massive prompt to the `LLMHandler`. The entire logic of parsing, validation, and response processing happens here. It contains the retry loop.

-   **Response Parsing (`_parse_and_validate_response` and `_process_valid_response`)**:
    -   `_parse_and_validate_response` uses the pre-compiled regex from `_update_dynamic_patterns` to perform strict validation. A response is only valid if it contains `{thinking: ...}` and `{{self-prompt-from-{NAME}}: ...}` blocks. This is a non-negotiable rule that forces the agent to maintain its internal state loop.
    -   `_process_valid_response` is called only after a response is validated. It uses regex `findall` and `finditer` to extract all commands and speech blocks. It then dispatches each command to `_execute_agent_command`.

-   **Command System (`_execute_agent_command` and helpers)**:
    -   `_execute_agent_command` is a router. It uses a series of `re.fullmatch` or `re.match` checks to determine which specific command handler to call (e.g., `_handle_read_command`).
    -   The `_handle_*_command` methods contain the actual file I/O logic. They use `_get_secure_path` to prevent path traversal attacks (e.g., `delete-file-../../important.dat`).
    -   These handlers are responsible for reading/writing files and, critically, for formatting the feedback strings (e.g., `file-created`, `file-not-found`) using the templates loaded from `config.json`. This feedback is appended to `self.file_content_for_next_turn` and forces an immediate subsequent turn, allowing the agent to "see" the result of its action right away.

-   **Memory System (`_handle_memory_consolidation`)**:
    -   This is a recursive process that uses the LLM to manage its own memory.
    -   After a successful turn, the *entire raw response* from the LLM is passed to `_summarize_text` with the STM summarizer prompt.
    -   The result becomes a new STM entry.
    -   The method then checks if the capacity of each memory tier (STM, MTM, LTM) has been exceeded.
    -   If a tier is full, it takes a batch of the oldest memories, joins them into a single block of text, and calls `_summarize_text` again with the appropriate MTM or LTM summarizer prompt.
    -   The new, consolidated memory is added to the next tier up, and the old memories are deleted. This mimics a hierarchical memory consolidation process.

### `gui.py` - The Face of the Application

This file contains the `App` class which inherits from `tk.Tk`. It is designed to be as "dumb" as possible; its primary job is to render what it's told and send user actions to the backend.

-   **`__init__`**:
    -   Sets up the main window, styles, fonts, and the main `PanedWindow` layout.
    -   Loads layout configurations (`window_sizes`, `right_pane_order`) from the config.
    -   Calls the `_create_*` helper methods to build all the widgets.
    -   It defines many `tk.StringVar`, `IntVar`, etc., which are bound to the widgets. These variables are the single source of truth for the settings displayed in the UI.
    -   Crucially, it starts the `process_incoming` loop with `self.after(100, self.process_incoming)`.

-   **`process_incoming`**: This is the GUI's main loop. It polls the `manager_to_ui_q` for new messages from the `ChatManager`. The large `if/elif` block here is a message dispatcher that calls the appropriate UI update function based on the message `type`. For example, a message `{"type": "update_memory_log", "payload": ...}` will trigger a call to `self.update_memory_log(payload)`.

-   **UI Update Methods (`add_chat_message`, `update_memory_log`, etc.)**: These methods directly manipulate the Tkinter widgets. They follow a standard pattern:
    1.  `widget.config(state=tk.NORMAL)`
    2.  `widget.delete(...)` / `widget.insert(...)`
    3.  `widget.config(state=tk.DISABLED)`
    4.  `widget.see(tk.END)` (to auto-scroll)
    This pattern ensures that the user cannot type directly into the log windows.

-   **Settings and Event Handlers (`_save_all_settings`, `_open_*_window`)**:
    -   Methods for opening popup windows (`Toplevel`) are self-contained. They build the window, and the "Save" or "Apply" button in the popup typically either updates the local `tk.IntVar`s/`StringVar`s or sends a message directly to the `ChatManager`.
    -   `_save_all_settings` is a master function that gathers the current state of *all* the setting variables (`self.param_vars`, `self.auto_turn_var`, etc.) and the window geometry (`self.winfo_width()`) into a single large dictionary. It then puts this on the `ui_to_manager_q` with the type `save_all_settings`. The `ChatManager` is responsible for actually writing this to `config.json`.

---

## 3. Communication Protocol: The Queues

The contract between the GUI and the ChatManager is defined by the message format. Every message is a dictionary containing `type` (a string) and `payload` (any data type).

-   **GUI -> ChatManager (`input_q`) Examples**:
    -   `{"type": "user_message", "payload": "Hello, agent."}`
    -   `{"type": "hard_reset", "payload": None}`
    -   `{"type": "update_auto_turn_state", "payload": True}`
    -   `{"type": "save_all_settings", "payload": {<large dict of all settings>}}`

-   **ChatManager -> GUI (`output_q`) Examples**:
    -   `{"type": "new_message", "payload": {"sanitized_message": "Hello!", "raw_log": "...", "usage": ...}}`
    -   `{"type": "update_memory_log", "payload": {"stm": [...], "mtm": [...], "ltm": [...]}}`
    -   `{"type": "status_update", "payload": {"llm_status": "Generating..."}}`
    -   `{"type": "api_key_validation_status", "payload": False}`

---

## 4. Persistence & State Management

State is managed in three locations:

1.  **`ChatManager` Memory**: The live, in-memory state of the agent (e.g., `self.memory`, `self.recent_chat_log`). This is the most current state.
2.  **`config.json`**: This file persists settings and *session state* between runs. The `ChatManager` is responsible for saving its volatile state (like `chat_history` and `last_self_prompt`) to this file upon clean shutdown or when `_save_config` is called.
3.  **File System (`/prompts`, `/memory`, `/terminal`)**:
    -   `/prompts`: Core identity files. Loaded once on startup but can be reloaded/saved via the UI.
    -   `/memory`: A more robust persistence layer for the agent's mind. Each tier (stm, mtm, ltm) has its own JSON file. `ChatManager` saves to these files after every consolidation cycle, ensuring memory is not lost even if the application crashes.
    -   `/terminal`: The agent's sandboxed working directory. Its contents are volatile and intended to be managed by the agent itself.

---

## 5. How to Extend the Project

This architecture is designed to be extensible.

### Adding a New Agent Command (e.g., a Calculator)

Let's add a command `{calculate: 2+2}`.

1.  **Define Syntax**: Decide on the command format. `{calculate: ...}` is a good choice.

2.  **Update Regex (`chat_manager.py`)**: In `_update_dynamic_patterns`, add the new pattern to `all_recognized_commands_pattern` and `agent_commands`.
    `...|r"calculate\s*:.*"...)`

3.  **Create Handler (`chat_manager.py`)**: Write the function that performs the action.
    `def _handle_calculate_command(self, expression: str) -> str:
        try:
            result = eval(expression) # DANGEROUS, use a safe eval library in a real app!
            template = self.prompt_templates.get('calculate_success', '')
            return template.replace('__EXPRESSION__', expression).replace('__RESULT__', str(result))
        except Exception as e:
            template = self.prompt_templates.get('calculate_error', '')
            return template.replace('__EXPRESSION__', expression).replace('__ERROR__', str(e))`

4.  **Route the Command (`chat_manager.py`)**: In `_execute_agent_command`, add the routing logic.
    `calculate_match = re.match(r"calculate\s*:\s*(.*)", command, re.DOTALL | re.IGNORECASE)
    if calculate_match: feedback = self._handle_calculate_command(calculate_match.group(1).strip())`

5.  **Add Feedback Templates (`main.py` and `config.json`)**: In `get_default_config()` in `main.py`, add the new prompt templates.
    `"calculate_success": "{Terminal: calculation-complete[__EXPRESSION__=__RESULT__]}",
    "calculate_error": "{Terminal: calculation-failed[__EXPRESSION__][Error: __ERROR__]}"`
    If you have an existing `config.json`, add these keys manually.

6.  **Instruct the Agent (`Main Prompt`)**: Edit your main system prompt to teach the agent about its new skill.
    `You have a calculator tool. To use it, generate the command in the format {calculate: mathematical_expression}. For example: {calculate: 5*10}.`

### Adding a New GUI Control

Let's add a button to clear the Raw LLM Log pane.

1.  **Add Widget (`gui.py`)**: In `_create_right_pane`, underneath the `ttk.Label` for the Raw Log, add a button.
    `clear_log_btn = ttk.Button(self.raw_log_frame, text="Clear", command=self._clear_raw_log_pane)`
    `clear_log_btn.pack(side=tk.RIGHT)`

2.  **Create Handler (`gui.py`)**: Write the method that the button calls. This method does NOT need to talk to the ChatManager, as it's a purely cosmetic UI action.
    `def _clear_raw_log_pane(self):
        self._clear_text_widget(self.log_text)`
    (Note: `_clear_text_widget` is a pre-existing helper function).

### Integrating a Different LLM (e.g., Anthropic Claude)

1.  **Create New Handler**: Create `claude_handler.py`.
2.  **Implement the Interface**: The `ClaudeHandler` class must have:
    -   `__init__(self, api_key)`
    -   `update_api_key(self, api_key)`: This would configure the Anthropic client.
    -   `generate_response(self, prompt, params)`: This would call `anthropic.Anthropic().messages.create(...)`, receive the response, and format the output into the required dictionary: `{"choices": [{"text": response.content[0].text}], "usage": {"prompt_tokens": ..., "completion_tokens": ...}}`.
3.  **Swap in `ChatManager`**:
    -   In `chat_manager.py`, change `from llm_handler import LLMHandler` to `from claude_handler import ClaudeHandler`.
    -   In `_initialize_llm_handler`, change `self.llm_handler = LLMHandler(...)` to `self.llm_handler = ClaudeHandler(...)`.
4.  **Update API Key UI**: In `gui.py`, you might want to change the text in `_open_api_key_window` to refer to Anthropic instead of Google.

The rest of the application will work seamlessly because the `ChatManager` only ever interacts with the handler through this standardized interface.