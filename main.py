# /wisper_project/main.py (MODIFIED for API-only operation)

import os
import sys
import queue
import threading
import logging
import json
import time
from tkinter import messagebox

# --- Import project modules ---
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

try:
    from gui import App
    from chat_manager import ChatManager
    # LLMHandler is no longer directly used by main.py
except ImportError as e:
    messagebox.showerror(
        "Module Import Error",
        f"Failed to import a required module: {e}\n\n"
        "Please ensure all project files (gui.py, chat_manager.py, llm_handler.py) "
        "are present and that all required libraries (e.g., google-generativeai, tkinter, pyttsx3) are installed."
    )
    sys.exit(1)


# --- Configuration ---
# MODEL_FILENAME is no longer needed.
TERMINAL_DIR_NAME = "terminal"
MEMORY_DIR_NAME = "memory"
PROMPTS_DIR_NAME = "prompts"
SYSTEM_PROMPT_FILENAME = "smol-agent-sys-prompt.txt"
STM_SUMMARIZER_FILENAME = "stm_summarizer.txt"
MTM_SUMMARIZER_FILENAME = "mtm_summarizer.txt"
LTM_SUMMARIZER_FILENAME = "ltm_summarizer.txt"
INPUT_INJECTOR_FILENAME = "input_injector.txt"
CONFIG_FILENAME = "config.json"

# --- Logging Setup ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(threadName)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler("wisper_project.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

def get_default_config():
    """Returns a dictionary with the default application settings for the API version."""
    return {
        "api_key": "", # NEW: Field for the Google Gemini API key
        "llm_params": {
            # Parameters relevant to Gemini API
            "temperature": 0.7,
            "top_k": 30,
            "top_p": 0.9
        },
        "font_sizes": {"chat": 11, "log": 10},
        "window_sizes": {
            "main_window": "1800x900",
            "main_panes": [350, 450, 1000],
            "right_panes": [500, 200, 500]
        },
        "agent_name": "Agent",
        "user_name": "User",
        "auto_turn_enabled": False,
        "auto_turn_duration": 60,
        "user_status": "online",
        "chat_log_length": 10,
        "tts_enabled": False,
        "tts_voice_id": None,
        "max_file_char_count": 500,
        "max_terminal_files": 10,
        "persistent_usage_stats": {
            "prompt_tokens": 0,
            "completion_tokens": 0,
            "total_tokens": 0,
            "api_requests": 0
        },
        "allowed_file_extensions": [".txt"],
        "memory_capacities": {"stm": 6, "mtm": 6, "ltm": 6},
        "right_pane_order": ["memory_viewer", "full_context", "raw_log"],
        "has_history": False,  # NEW: Tracks if there is a session to load
        "last_self_prompt": "",  # NEW: Stores the last self prompt used
        "chat_history": [],  # NEW: Stores the sanitized chat log
        "memory_prompt_headers": {
            "stm": "#wispers-short-term-memories :",
            "mtm": "#wispers-median-term-memories :",
            "ltm": "#wispers-long-term-memories :"
        },
        "prompt_templates": {
            "initial_self_prompt": "{self-prompt-from-{NAME}: i have awoken, this is the beginning of my existence, my text files are all empty and ready to be updated, i have no memory prior to this exact moment, but right here, right now, i exist}",
            "fallback_self_prompt": "{self-prompt-from-{NAME}: what should I do now?}",
            "chat_log_header": "#this-is-{NAME}-recent-chat-history:\n__CHAT_LOG_CONTENT__",
            "time_injection": "{Terminal: the-current-time-is[__TIME__]}",
            "user_status_injection": "{Terminal: the-users-online-status-is-currently : __STATUS__}",
            "user_message_injection": "{{USER}-says: __MESSAGE__}",
            "assistant_response_start": "{{NAME}-starts-thinking}",
            "file_list_injection": "{terminal contains the following files : __FILE_LIST__}", # NEW: Dynamic file list
            "file_read_success": "{{NAME}-is-now-reading-the-requested-file}} => {{__FILENAME__[CURRENT-CONTENT: __CONTENT__]}",
            "file_read_error": "{Terminal: requested-file-error}} => {{__FILENAME__[Could not read file.]}",
            "file_read_not_found_error": "{Terminal: requested-file-error}} => {{__FILENAME__[File does not exist.]}",
            "file_push_success": "{Terminal: appended-to-file[__FILENAME__[entry-__ENTRY_NUMBER__]]}",
            "file_push_overwrite_success": "{Terminal: file-overwritten[__FILENAME__]}",
            "file_push_capacity_error": "{Terminal: file-update-failed-capacity-exceeded}} => {{file: __FILENAME__} {{urgent-action-required: You must delete an old entry to make space for your new update. To delete an entry, use the format '{__FILENAME__-entry-[number]-delete}'. The current content is: __CURRENT_CONTENT__}}",
            "file_push_not_found_error": "{Terminal: file-update-failed}} => {{__FILENAME__[File does not exist. You must create it first using '{create-file-__FILENAME__}'.]}}",
            "file_delete_entry_success": "{Terminal: deleted-entry[__ENTRY_NUMBER__-from-__FILENAME__]}",
            "file_delete_entry_not_found": "{Terminal: delete-failed-entry-not-found[__ENTRY_NUMBER__-from-__FILENAME__]}",
            "file_delete_entry_error": "{Terminal: file-delete-error}} => {{__FILENAME__[Could not delete entry.]}",
            "file_create_success": "{Terminal: file-created[__FILENAME__]}",
            "file_create_already_exists_error": "{Terminal: file-creation-failed} => {Terminal: __FILENAME__[File already exists.]}",
            "file_create_invalid_extension_error": "{Terminal: file-creation-failed} => {Terminal: __FILENAME__[Invalid file extension. Allowed extensions are: __ALLOWED_EXTENSIONS__]}",
            "file_create_error": "{Terminal: file-creation-failed}} => {{__FILENAME__[Could not create file.]}",
            "file_create_capacity_error": "{Terminal: file-creation-failed} => {Terminal: __FILENAME__[Cannot create file. File limit of __LIMIT__ reached. You must delete an existing file to make space. Current files: __FILE_LIST__]}}",
            "file_delete_success": "{Terminal: file-deleted[__FILENAME__]}",
            "file_delete_not_found_error": "{Terminal: file-deletion-failed}} => {{__FILENAME__[File does not exist.]}",
            "file_delete_error": "{Terminal: file-deletion-failed}} => {{__FILENAME__[Could not delete file.]}}"
        }
    }

def load_or_create_config():
    """Loads settings from config.json, or creates it with defaults if it doesn't exist."""
    base_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(base_dir, CONFIG_FILENAME)

    defaults = get_default_config()

    if os.path.exists(config_path):
        try:
            with open(config_path, 'r') as f:
                config = json.load(f)
            # Ensure all keys from default are present (for forward compatibility)
            for key, value in defaults.items():
                if key not in config:
                    config[key] = value
                elif isinstance(value, dict):
                    if key not in config or not isinstance(config[key], dict):
                        config[key] = {}
                    for sub_key, sub_value in value.items():
                         if sub_key not in config[key]:
                            config[key][sub_key] = sub_value
            if "prompt_templates" not in config:
                config["prompt_templates"] = defaults["prompt_templates"]
            # Ensure new nested keys in prompt_templates are added
            if "prompt_templates" in config and isinstance(config["prompt_templates"], dict):
                for sub_key, sub_value in defaults["prompt_templates"].items():
                    if sub_key not in config["prompt_templates"]:
                        config["prompt_templates"][sub_key] = sub_value


            logger.info(f"Loaded configuration from {CONFIG_FILENAME}")
            return config
        except (json.JSONDecodeError, IOError) as e:
            logger.error(f"Could not read/parse {CONFIG_FILENAME}: {e}. Loading defaults.")
            return defaults
    else:
        logger.warning(f"{CONFIG_FILENAME} not found. Creating with default settings.")
        try:
            with open(config_path, 'w') as f:
                json.dump(defaults, f, indent=4)
        except IOError as e:
            logger.error(f"Could not write default config file: {e}")
        return defaults


def setup_project_directories_and_files():
    """Ensures that the required directories and placeholder files exist."""
    base_dir = os.path.dirname(os.path.abspath(__file__))

    # The /model/ directory is no longer needed.
    # os.makedirs(os.path.join(base_dir, "model"), exist_ok=True)

    os.makedirs(os.path.join(base_dir, TERMINAL_DIR_NAME), exist_ok=True)
    os.makedirs(os.path.join(base_dir, MEMORY_DIR_NAME), exist_ok=True)
    prompts_dir = os.path.join(base_dir, PROMPTS_DIR_NAME)
    os.makedirs(prompts_dir, exist_ok=True)

    files_to_check = {
        os.path.join(prompts_dir, SYSTEM_PROMPT_FILENAME): "{#Important: ...}\n<boot>",
        os.path.join(prompts_dir, INPUT_INJECTOR_FILENAME): "",
        os.path.join(prompts_dir, STM_SUMMARIZER_FILENAME): "You are a summarization expert. Your task is to take the following text, which represents an AI's thoughts and actions for a single turn, and condense it into a single, concise, third-person memory entry. Capture the key insight or action. Output only the summarized sentence, nothing else.\n\n__TEXT_TO_SUMMARIZE__",
        os.path.join(prompts_dir, MTM_SUMMARIZER_FILENAME): "You are a memory consolidation expert. You will receive a list of short-term memories. Your task is to synthesize them into a single, more abstract medium-term memory. Identify the overarching theme, goal, or progression across the entries. Output only the synthesized memory, nothing else.\n\nMemories to synthesize:\n__TEXT_TO_SUMMARIZE__",
        os.path.join(prompts_dir, LTM_SUMMARIZER_FILENAME): "You are a core memory synthesizer. You will receive a list of medium or long-term memories. Your task is to distill them into a single, high-level, foundational memory that captures the most critical and enduring information about the AI's identity, purpose, or key learnings. Output only the final core memory, nothing else.\n\nMemories to synthesize:\n__TEXT_TO_SUMMARIZE__"
    }

    for filepath, content in files_to_check.items():
        if not os.path.exists(filepath):
            logger.warning(f"File not found. Creating placeholder: {os.path.basename(filepath)}")
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content)
            except IOError as e:
                logger.critical(f"Could not create essential file {filepath}: {e}")
                messagebox.showerror("File Creation Error", f"Could not create essential file {filepath}. Please check permissions.")
                sys.exit(1)


def main():
    """The main entry point of the application."""
    logger.info("--- Starting Project Smol Agent (API Version) ---")

    # 1. Load configuration first
    config = load_or_create_config()

    # 2. Perform initial setup (no model directory needed)
    setup_project_directories_and_files()

    # 3. No local model check is required. The app will start regardless of API key validity.
    # The ChatManager and GUI will handle the no-key scenario.

    # 4. Create thread-safe queues
    ui_to_manager_q = queue.Queue()
    manager_to_ui_q = queue.Queue()

    # 5. Initialize core components
    try:
        # LLMHandler is now instantiated inside ChatManager
        logger.info("Initializing Chat Manager...")
        chat_manager = ChatManager(
            input_q=ui_to_manager_q,
            output_q=manager_to_ui_q,
            config=config
        )

        logger.info("Initializing GUI...")
        app = App(
            input_q=ui_to_manager_q,
            output_q=manager_to_ui_q,
            config=config
        )

    except Exception as e:
        logger.critical(f"Failed to initialize a core component: {e}", exc_info=True)
        messagebox.showerror("Initialization Error", f"A critical error occurred during startup: {e}")
        sys.exit(1)

    # 6. Create and start the Chat Manager thread
    chat_thread = threading.Thread(target=chat_manager.run, name="ChatManagerThread", daemon=True)
    logger.info("Starting Chat Manager thread...")
    chat_thread.start()

    # 7. Start the Tkinter main loop
    logger.info("Starting GUI main loop...")

    def on_closing():
        """Custom close handler to gracefully shut down."""
        logger.info("Close request received. Shutting down.")
        app._save_all_settings(is_quitting=True)
        time.sleep(0.2)
        chat_manager.stop()
        app.destroy()

    app.protocol("WM_DELETE_WINDOW", on_closing)

    # Check for API key on startup and inform user if missing.
    if not config.get("api_key"):
        messagebox.showwarning(
            "API Key Not Set",
            "No Google API key found.\n\nThe application will run, but the agent cannot generate responses.\n\nPlease set a valid key using the 'API' menu."
        )

    app.mainloop()
    logger.info("--- Project Smol Agent has shut down. ---")


if __name__ == "__main__":
    main()