# /wisper_project/chat_manager.py (MODIFIED)

import logging
import queue
import re
import os
import threading
import time
import json
from datetime import datetime
from collections import deque
from typing import Dict, Any, Optional, Tuple, List
import platform

# --- Third-party library for Text-to-Speech ---
try:
    import pyttsx3
except ImportError:
    pyttsx3 = None

# --- Import pythoncom for Windows COM initialization ---
try:
    import pythoncom
    IS_WINDOWS = platform.system() == "Windows"
except ImportError:
    pythoncom = None
    IS_WINDOWS = False

from llm_handler import LLMHandler

# Configure logging for this module
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# Constants
MAX_RETRIES = 3
TERMINAL_DIR_NAME = "terminal"
MEMORY_DIR_NAME = "memory"
PROMPTS_DIR_NAME = "prompts"
SYSTEM_PROMPT_FILENAME = "smol-agent-sys-prompt.txt"
STM_SUMMARIZER_FILENAME = "stm_summarizer.txt"
MTM_SUMMARIZER_FILENAME = "mtm_summarizer.txt"
LTM_SUMMARIZER_FILENAME = "ltm_summarizer.txt"
INPUT_INJECTOR_FILENAME = "input_injector.txt"
CONFIG_FILENAME = "config.json"
VALID_FILENAME_PATTERN = re.compile(r'^[a-zA-Z0-9_\-]+\.[a-zA-Z0-9]+$')


class ChatManager:
    """
    The core logic engine for the Smol Agent. Runs in a dedicated thread
    to handle all backend operations without blocking the GUI.
    """

    def __init__(self, input_q: queue.Queue, output_q: queue.Queue, config: Dict[str, Any]):
        self.input_q = input_q
        self.output_q = output_q
        self.config = config
        self.is_running = threading.Event()
        self.is_running.set()

        self.llm_handler: Optional[LLMHandler] = None

        self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.prompts_dir = os.path.join(self.base_dir, PROMPTS_DIR_NAME)
        self.system_prompt_path = os.path.join(self.prompts_dir, SYSTEM_PROMPT_FILENAME)
        self.stm_summarizer_path = os.path.join(self.prompts_dir, STM_SUMMARIZER_FILENAME)
        self.mtm_summarizer_path = os.path.join(self.prompts_dir, MTM_SUMMARIZER_FILENAME)
        self.ltm_summarizer_path = os.path.join(self.prompts_dir, LTM_SUMMARIZER_FILENAME)
        self.injector_path = os.path.join(self.prompts_dir, INPUT_INJECTOR_FILENAME)
        self.config_path = os.path.join(self.base_dir, CONFIG_FILENAME)
        self.terminal_dir = os.path.join(self.base_dir, TERMINAL_DIR_NAME)
        self.memory_dir = os.path.join(self.base_dir, MEMORY_DIR_NAME)

        self.api_key: str = self.config.get("api_key", "")
        self.prompt_templates: Dict[str, str] = self.config.get("prompt_templates", self._get_default_prompt_templates())
        self.system_prompt: str = ""
        self.input_injector: str = ""
        self.llm_params: Dict[str, Any] = self.config.get("llm_params", self._get_default_llm_params())
        self.user_status: str = self.config.get("user_status", "online")
        self.chat_log_length: int = self.config.get("chat_log_length", 10)
        self.auto_turn_enabled: bool = self.config.get("auto_turn_enabled", False)
        self.auto_turn_interval: int = self.config.get("auto_turn_duration", 60)
        self.max_file_char_count: int = self.config.get("max_file_char_count", 500)
        self.max_terminal_files: int = self.config.get("max_terminal_files", 10)
        self.agent_name: str = self.config.get("agent_name", "Agent")
        self.user_name: str = self.config.get("user_name", "User")
        self.memory_capacities: Dict[str, int] = self.config.get("memory_capacities", {"stm": 6, "mtm": 6, "ltm": 6})
        self.memory_prompt_headers: Dict[str, str] = self.config.get("memory_prompt_headers", {})
        self.right_pane_order: List[str] = self.config.get("right_pane_order", ["memory_viewer", "full_context", "raw_log"])
        self.allowed_file_extensions: List[str] = self.config.get("allowed_file_extensions", [".txt"])
        
        self.persistent_usage_stats: Dict[str, int] = self.config.get("persistent_usage_stats", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_requests": 0})

        # --- State Loading from Config ---
        self.has_history = self.config.get("has_history", False)
        self.chat_history_on_load = self.config.get("chat_history", [])
        last_self_prompt_on_load = self.config.get("last_self_prompt", "")

        if self.has_history and last_self_prompt_on_load:
            self.current_self_prompts = last_self_prompt_on_load.split('\n')
        else:
            self.current_self_prompts = [self.prompt_templates.get("initial_self_prompt", "")]
        
        if self.has_history and self.chat_history_on_load:
            self.recent_chat_log = deque(self.chat_history_on_load, maxlen=self.chat_log_length)
        else:
            self.recent_chat_log = deque(maxlen=self.chat_log_length)
        
        # --- Volatile State ---
        self.file_content_for_next_turn: str = ""
        self.last_activity_timestamp: float = time.monotonic()
        self.pending_user_messages = deque()
        self.force_next_turn: bool = False
        self.idle_turn_counter: int = 0
        self.user_is_typing: bool = False
        self.pending_file_read: Optional[str] = None

        self.memory: Dict[str, List[str]] = {"stm": [], "mtm": [], "ltm": []}

        self.tts_enabled: bool = self.config.get("tts_enabled", False)
        self.tts_voice_id: Optional[str] = self.config.get("tts_voice_id", None)
        self.tts_queue = queue.Queue()
        self.is_speaking = threading.Event()
        self.is_speaking.set()
        self.tts_thread = threading.Thread(target=self._tts_worker, name="TTSWorkerThread", daemon=True)
        self.unlock_gui_after_tts: bool = False

        self._ensure_terminal_dir_exists()
        self._ensure_memory_dir_exists()

        self.patterns: Dict[str, re.Pattern] = {}
        self.all_recognized_commands_pattern: Optional[re.Pattern] = None
        self._update_dynamic_patterns()
        
        # Send initial token counts to GUI on startup
        self._send_to_gui({"type": "update_persistent_stats", "payload": self.persistent_usage_stats})

    def _update_dynamic_patterns(self):
        agent_name_pattern = re.escape(self.agent_name)
        self.all_recognized_commands_pattern = re.compile(
            rf"(\{{s*thinking\s*:.*?\}}|"
            rf"{{s*{agent_name_pattern}\s*-\s*says\s*:.*?\}}|"
            rf"{{s*self\s*-\s*prompt\s*-\s*from\s*-\s*{agent_name_pattern}\s*:.*?\}}|"
            rf"{{s*read\s*-\s*file\s*-\s*[\w\.\-]+\s*\}}|"
            rf"{{s*push\s*-\s*update\s*-\s*[\w\.\-]+\s*:\s*.*?\}}|"
            rf"{{s*[\w\.\-]+\s*-\s*entry\s*-\s*\d+\s*-\s*delete\s*\}}|"
            rf"{{s*create\s*-\s*file\s*-\s*[\w\.\-]+\s*\}}|"
            rf"{{s*delete\s*-\s*file\s*-\s*[\w\.\-]+\s*\}}|"
            rf"{{s*ping-user\s*\}})",
            re.DOTALL | re.IGNORECASE
        )
        self.patterns = {
            "thinking": re.compile(r"\{\s*thinking\s*:\s*(.*?)\s*\}", re.DOTALL | re.IGNORECASE),
            "agent_says": re.compile(rf"{{s*{agent_name_pattern}\s*-\s*says\s*:\s*(.*?)\s*\}}", re.DOTALL | re.IGNORECASE),
            "self_prompt_content": re.compile(rf"{{s*self\s*-\s*prompt\s*-\s*from\s*-\s*{agent_name_pattern}\s*:\s*(.*?)\s*\}}", re.DOTALL | re.IGNORECASE),
            "all_self_prompts": re.compile(rf"(\{{s*self\s*-\s*prompt\s*-\s*from\s*-\s*{agent_name_pattern}\s*:.*?\}})", re.DOTALL | re.IGNORECASE),
            "agent_commands": re.compile(
                r"\{\s*(read\s*-\s*file\s*-\s*[\w\.\-]+|"
                r"push\s*-\s*update\s*-\s*[\w\.\-]+\s*:.*|"
                r"[\w\.\-]+\s*-\s*entry\s*-\s*\d+\s*-\s*delete|"
                r"create\s*-\s*file\s*-\s*[\w\.\-]+|"
                r"delete\s*-\s*file\s*-\s*[\w\.\-]+|"
                r"ping-user)\s*\}",
                re.DOTALL | re.IGNORECASE
            )
        }
        logger.info(f"Dynamic regex patterns updated for agent name: '{self.agent_name}'")

    def _get_default_llm_params(self) -> Dict[str, Any]:
        return {'temperature': 0.7, 'top_k': 30, 'top_p': 0.9}

    def _get_default_prompt_templates(self) -> Dict[str, str]:
        return {
            "initial_self_prompt": "{self-prompt-from-{NAME}: i have awoken, this is the beginning of my existence, my text files are all empty and ready to be updated, i have no memory prior to this exact moment, but right here, right now, i exist}",
            "fallback_self_prompt": "{self-prompt-from-{NAME}: what should I do now?}",
            "chat_log_header": "#this-is-{NAME}-recent-chat-history:\n__CHAT_LOG_CONTENT__",
            "time_injection": "{Terminal: the-current-time-is[__TIME__]}",
            "user_status_injection": "{Terminal: the-users-online-status-is-currently : __STATUS__}",
            "user_message_injection": "{{USER}-says: __MESSAGE__}",
            "assistant_response_start": "{{NAME}-starts-thinking}",
            "file_list_injection": "{terminal contains the following files : __FILE_LIST__}",
            "file_read_success": "{{NAME}-is-now-reading-the-requested-file}} => {{__FILENAME__[CURRENT-CONTENT: __CONTENT__]}}",
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

    def _ensure_terminal_dir_exists(self):
        os.makedirs(self.terminal_dir, exist_ok=True)

    def _ensure_memory_dir_exists(self):
        os.makedirs(self.memory_dir, exist_ok=True)

    def run(self):
        logger.info("Chat Manager thread started.")
        self._initialize_llm_handler()
        self._initialize_tts()
        self.tts_thread.start()
        self._load_system_prompt()
        self._load_input_injector()
        self._initialize_memory()
        
        # Send loaded chat history to GUI on startup
        if self.has_history and self.chat_history_on_load:
            self._send_to_gui({"type": "load_chat_history", "payload": self.chat_history_on_load})

        while self.is_running.is_set():
            try:
                if not self.is_speaking.is_set():
                    self.is_speaking.wait(timeout=0.5)
                    continue

                self._process_incoming_commands()
                if self._should_trigger_turn():
                    self._execute_turn()

                time_since_activity = time.monotonic() - self.last_activity_timestamp
                countdown = max(0, self.auto_turn_interval - time_since_activity)

                if not self.is_speaking.is_set(): countdown_text = "Self-prompting paused (speaking...)"
                elif self.user_is_typing: countdown_text = "Self-prompting paused (typing...)"
                elif not self.auto_turn_enabled: countdown_text = "Auto-turn is OFF"
                else: countdown_text = f"Time until self prompt: {int(countdown)}s"

                self._send_to_gui({"type": "status_update", "payload": {"turn_timer": countdown_text}})
                time.sleep(0.5)
            except Exception as e:
                logger.critical(f"Unhandled exception in Chat Manager loop: {e}", exc_info=True)
                self._send_to_gui({"type": "error", "payload": "A critical error occurred in the Chat Manager."})
                self.stop()
        logger.info("Chat Manager thread stopped.")

    def stop(self):
        self.is_running.clear()

    def _initialize_llm_handler(self):
        logger.info("Initializing LLM Handler with stored API key.")
        self.llm_handler = LLMHandler(api_key=self.api_key)
        self._send_to_gui({"type": "api_key_validation_status", "payload": self.llm_handler.api_key_is_valid})
        
    def _initialize_tts(self):
        if pyttsx3 is None:
            logger.error("pyttsx3 library not found. TTS functionality will be disabled.")
            return
        
        try:
            logger.info("Getting TTS voice list...")
            temp_engine = pyttsx3.init()
            voices = temp_engine.getProperty('voices')
            voice_list_for_gui = [{'name': f"{v.name} ({getattr(v, 'age', 'N/A')})", 'id': v.id} for v in voices]
            temp_engine.stop()
            
            if self.tts_voice_id and self.tts_voice_id not in [v['id'] for v in voice_list_for_gui]:
                self.tts_voice_id = None
            
            if not self.tts_voice_id and voice_list_for_gui:
                self.tts_voice_id = voice_list_for_gui[0]['id']

            self._send_to_gui({"type": "tts_voices_list", "payload": voice_list_for_gui})
            logger.info(f"Sent {len(voice_list_for_gui)} voices to GUI.")
        except Exception as e:
            logger.error(f"Failed to get TTS voice list: {e}", exc_info=True)

    def _tts_worker(self):
        tts_engine = None
        if IS_WINDOWS and pythoncom:
            pythoncom.CoInitialize()

        while self.is_running.is_set():
            try:
                text_to_speak, voice_id, on_done_callback = self.tts_queue.get(timeout=1)
                if tts_engine is None:
                    tts_engine = pyttsx3.init()
                
                try:
                    tts_engine.setProperty('voice', voice_id)
                    tts_engine.say(text_to_speak)
                    tts_engine.runAndWait()
                except Exception as e:
                    logger.error(f"Error during TTS generation: {e}", exc_info=True)
                finally:
                    if on_done_callback:
                        on_done_callback()
            except queue.Empty:
                continue
            except Exception as e:
                logger.error(f"Unhandled exception in TTS worker thread: {e}", exc_info=True)
        
        if tts_engine:
            tts_engine.stop()

    def _load_system_prompt(self):
        try:
            with open(self.system_prompt_path, 'r', encoding='utf-8') as f: self.system_prompt = f.read()
            self._send_to_gui({"type": "system_prompt_loaded", "payload": self.system_prompt})
        except FileNotFoundError:
            self.system_prompt = "CRITICAL ERROR: System prompt file not found."
            self._send_to_gui({"type": "error", "payload": self.system_prompt})
            self.stop()

    def _load_input_injector(self):
        try:
            with open(self.injector_path, 'r', encoding='utf-8') as f: self.input_injector = f.read()
            self._send_to_gui({"type": "input_injector_loaded", "payload": self.input_injector})
        except FileNotFoundError:
            self.input_injector = ""

    def _initialize_memory(self):
        logger.info("Initializing tiered memory system...")
        for tier in ["stm", "mtm", "ltm"]:
            filepath = os.path.join(self.memory_dir, f"{tier}.json")
            try:
                if os.path.exists(filepath):
                    with open(filepath, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                        if "entries" in data and isinstance(data["entries"], list):
                            self.memory[tier] = data["entries"]
                        else: self._create_empty_memory_file(filepath, tier)
                else: self._create_empty_memory_file(filepath, tier)
            except (json.JSONDecodeError, IOError) as e:
                self._create_empty_memory_file(filepath, tier)
        self._send_to_gui({"type": "status_update", "payload": {"memory": self.memory}})

    def _create_empty_memory_file(self, filepath, tier):
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({"entries": []}, f)
            self.memory[tier] = []
        except IOError as e:
            logger.error(f"Failed to create empty memory file at {filepath}: {e}")

    def _save_memory_tier(self, tier: str):
        filepath = os.path.join(self.memory_dir, f"{tier}.json")
        try:
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump({"entries": self.memory[tier]}, f, indent=4)
            return True
        except IOError as e:
            logger.error(f"Could not save memory file {filepath}: {e}")
            return False

    def _save_config(self):
        """Saves the main configuration settings including session state."""
        try:
            # --- Non-session settings ---
            self.config["api_key"] = self.api_key
            self.config["llm_params"] = self.llm_params
            self.config["user_status"] = self.user_status
            self.config["auto_turn_enabled"] = self.auto_turn_enabled
            self.config["auto_turn_duration"] = self.auto_turn_interval
            self.config["chat_log_length"] = self.chat_log_length
            self.config["tts_enabled"] = self.tts_enabled
            self.config["tts_voice_id"] = self.tts_voice_id
            self.config["max_file_char_count"] = self.max_file_char_count
            self.config["max_terminal_files"] = self.max_terminal_files
            self.config["agent_name"] = self.agent_name
            self.config["user_name"] = self.user_name
            self.config["memory_capacities"] = self.memory_capacities
            self.config["memory_prompt_headers"] = self.memory_prompt_headers
            self.config["right_pane_order"] = self.right_pane_order
            self.config["prompt_templates"] = self.prompt_templates
            self.config["allowed_file_extensions"] = self.allowed_file_extensions
            
            # --- Session-specific state ---
            self.config["has_history"] = bool(self.recent_chat_log)
            self.config["last_self_prompt"] = "\n".join(self.current_self_prompts) if self.current_self_prompts else ""
            self.config["chat_history"] = list(self.recent_chat_log)

            # Note: persistent_usage_stats is saved separately for performance

            with open(self.config_path, 'w') as f:
                json.dump(self.config, f, indent=4)
            logger.info(f"Configuration and session state saved to {self.config_path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}", exc_info=True)
            return False

    def _save_persistent_stats(self):
        """Saves only the persistent usage stats to the config file instantly."""
        try:
            # Read the whole config first to avoid overwriting other settings
            with open(self.config_path, 'r') as f:
                current_config = json.load(f)
            
            # Update only the stats part
            current_config["persistent_usage_stats"] = self.persistent_usage_stats
            
            # Write the updated config back
            with open(self.config_path, 'w') as f:
                json.dump(current_config, f, indent=4)
            logger.info("Persisted token usage stats updated.")
            return True
        except (IOError, json.JSONDecodeError) as e:
            logger.error(f"Failed to save persistent usage stats: {e}")
            return False

    def _perform_hard_reset(self):
        self.recent_chat_log.clear()
        self.current_self_prompts = [self.prompt_templates.get("initial_self_prompt", "")]
        self.file_content_for_next_turn = ""
        self.pending_user_messages.clear()
        self.force_next_turn = False
        self.idle_turn_counter = 0
        self.last_activity_timestamp = time.monotonic()
        self.auto_turn_enabled = False
        self.pending_file_read = None
        
        for filename in os.listdir(self.terminal_dir):
            filepath = os.path.join(self.terminal_dir, filename)
            try:
                if os.path.isfile(filepath):
                    with open(filepath, 'w', encoding='utf-8') as f: f.write("[empty]")
            except Exception as e:
                logger.error(f"Failed to wipe terminal file {filename}: {e}")

        for tier in ["stm", "mtm", "ltm"]:
            self.memory[tier] = []
            self._create_empty_memory_file(os.path.join(self.memory_dir, f"{tier}.json"), tier)

        # Clear history fields in config and save
        self.config["has_history"] = False
        self.config["last_self_prompt"] = ""
        self.config["chat_history"] = []
        self._save_config()

        self._send_to_gui({"type": "clear_all_ui_logs"})
        self._send_to_gui({"type": "set_auto_turn_state", "payload": False})
        self._send_to_gui({"type": "status_update", "payload": {"info": f"{self.agent_name} has been reset."}})

    def _process_incoming_commands(self):
        while not self.input_q.empty():
            try:
                command = self.input_q.get_nowait()
                cmd_type, payload = command.get("type"), command.get("payload")
                
                if cmd_type == "user_message": self.pending_user_messages.append(payload)
                elif cmd_type == "update_api_key":
                    self.api_key = payload
                    if self.llm_handler:
                        self.llm_handler.update_api_key(self.api_key)
                        self._send_to_gui({"type": "api_key_validation_status", "payload": self.llm_handler.api_key_is_valid})
                    self._save_config()
                elif cmd_type == "get_all_prompts":
                    prompt_data = {"system_prompt": self.system_prompt, "input_injector": self.input_injector, "prompt_templates": self.prompt_templates}
                    self._send_to_gui({"type": "all_prompts_data", "payload": prompt_data})
                elif cmd_type == "get_summarizer_prompts":
                    try:
                        with open(self.stm_summarizer_path, 'r', encoding='utf-8') as f: stm = f.read()
                        with open(self.mtm_summarizer_path, 'r', encoding='utf-8') as f: mtm = f.read()
                        with open(self.ltm_summarizer_path, 'r', encoding='utf-8') as f: ltm = f.read()
                        self._send_to_gui({"type": "summarizer_prompts_data", "payload": {"stm": stm, "mtm": mtm, "ltm": ltm}})
                    except Exception as e:
                        self._send_to_gui({"type": "error", "payload": f"Could not load summarizer prompts: {e}"})
                elif cmd_type == "reset_persistent_stats":
                    self.persistent_usage_stats["prompt_tokens"] = 0
                    self.persistent_usage_stats["completion_tokens"] = 0
                    self.persistent_usage_stats["total_tokens"] = 0
                    self._save_persistent_stats()
                    self._send_to_gui({"type": "update_persistent_stats", "payload": self.persistent_usage_stats})
                    self._send_to_gui({"type": "status_update", "payload": {"info": "Persistent token stats reset."}})
                elif cmd_type == "reset_api_requests":
                    self.persistent_usage_stats["api_requests"] = 0
                    self._save_persistent_stats()
                    self._send_to_gui({"type": "update_persistent_stats", "payload": self.persistent_usage_stats})
                    self._send_to_gui({"type": "status_update", "payload": {"info": "API request counter reset."}})
                elif cmd_type == "save_summarizer_prompts":
                    try:
                        if "stm" in payload: self._save_text_to_file(self.stm_summarizer_path, payload["stm"])
                        if "mtm" in payload: self._save_text_to_file(self.mtm_summarizer_path, payload["mtm"])
                        if "ltm" in payload: self._save_text_to_file(self.ltm_summarizer_path, payload["ltm"])
                        self._send_to_gui({"type": "status_update", "payload": {"info": "Summarizer prompts saved."}})
                    except Exception as e:
                        self._send_to_gui({"type": "error", "payload": f"Could not save summarizer prompts: {e}"})
                elif cmd_type == "save_main_prompt":
                    self.system_prompt = payload.get("system_prompt", self.system_prompt)
                    if self._save_text_to_file(self.system_prompt_path, self.system_prompt):
                        self._send_to_gui({"type": "status_update", "payload": {"info": "Main prompt saved."}})
                elif cmd_type == "save_system_prompts":
                    if "input_injector" in payload:
                        self.input_injector = payload["input_injector"]
                        self._save_text_to_file(self.injector_path, self.input_injector)
                    if "prompt_templates" in payload:
                        self.prompt_templates = payload["prompt_templates"]
                        self._save_config()
                    self._send_to_gui({"type": "status_update", "payload": {"info": "System & template prompts saved."}})
                elif cmd_type == "hard_reset": self._perform_hard_reset()
                elif cmd_type == "update_auto_turn_state":
                    self.auto_turn_enabled = payload
                    self.last_activity_timestamp = time.monotonic()
                elif cmd_type == "update_tts_state": self.tts_enabled = payload
                elif cmd_type == "update_tts_voice": self.tts_voice_id = payload
                elif cmd_type == "update_user_status":
                    self.user_status = payload
                    self.idle_turn_counter = 0
                elif cmd_type == "user_typing_status":
                    is_typing = payload
                    if is_typing and not self.user_is_typing:
                        self.last_activity_timestamp = time.monotonic()
                    self.user_is_typing = is_typing
                elif cmd_type == "save_all_settings":
                    self.llm_params.update(payload.get("llm_params", {}))
                    self.api_key = payload.get("api_key", self.api_key)
                    self.user_status = payload.get("user_status", self.user_status)
                    self.auto_turn_enabled = payload.get("auto_turn_enabled", self.auto_turn_enabled)
                    self.tts_enabled = payload.get("tts_enabled", self.tts_enabled)
                    self.tts_voice_id = payload.get("tts_voice_id", self.tts_voice_id)
                    self.right_pane_order = payload.get("right_pane_order", self.right_pane_order)
                    self.memory_capacities = payload.get("memory_capacities", self.memory_capacities)
                    self.max_file_char_count = payload.get("max_file_char_count", self.max_file_char_count)
                    self.max_terminal_files = payload.get("max_terminal_files", self.max_terminal_files)
                    self.user_name = payload.get("user_name", self.user_name)
                    
                    new_agent_name = payload.get("agent_name", self.agent_name)
                    if new_agent_name != self.agent_name:
                        self.agent_name = new_agent_name
                        self._update_dynamic_patterns()

                    self.auto_turn_interval = payload.get("auto_turn_duration", self.auto_turn_interval)
                    
                    new_chat_log_len = payload.get("chat_log_length", self.chat_log_length)
                    if new_chat_log_len != self.chat_log_length:
                        self.chat_log_length = new_chat_log_len
                        self.recent_chat_log = deque(list(self.recent_chat_log), maxlen=self.chat_log_length)
                    
                    self.config.update(payload)
                    self._save_config()
                    self._send_to_gui({"type": "status_update", "payload": {"info": "Settings saved."}})

            except queue.Empty: break
            except Exception as e: logger.error(f"Error processing command from GUI: {e}", exc_info=True)

    def _should_trigger_turn(self) -> bool:
        if self.force_next_turn: return True
        is_user_turn = bool(self.pending_user_messages)
        auto_turn_time_elapsed = time.monotonic() - self.last_activity_timestamp > self.auto_turn_interval
        is_auto_turn = (self.auto_turn_enabled and auto_turn_time_elapsed and
                        self.user_status != 'offline' and not self.user_is_typing)
        return is_user_turn or is_auto_turn

    def _execute_turn(self):
        if self.force_next_turn:
            self.force_next_turn = False
        
        if not self.llm_handler or not self.llm_handler.api_key_is_valid:
            logger.error("Turn execution aborted: LLM handler is not ready or API key is invalid.")
            self._send_to_gui({"type": "error", "payload": "Cannot generate response. API key is missing, invalid, or could not be verified."})
            if self.pending_user_messages:
                self.pending_user_messages.clear()
                self._send_to_gui({"type": "user_input_processed"})
            return

        self._send_to_gui({"type": "status_update", "payload": {"llm_status": "Generating..."}})

        if self.pending_user_messages and self.user_status != 'online':
            self.user_status = 'online'
            self._send_to_gui({"type": "set_user_status", "payload": "online"})
            self.idle_turn_counter = 0

        user_message_for_this_turn = " ".join(self.pending_user_messages) if self.pending_user_messages else None
        
        prompt_for_this_turn, dynamic_input_for_log = self._construct_prompt_from_state()

        self._send_to_gui({"type": "update_full_context", "payload": {"full_context": prompt_for_this_turn}})

        self._send_to_gui({"type": "log_input", "payload": {"log_content": dynamic_input_for_log, "tag": "input_log"}})

        response_succeeded = False
        is_speaking_this_turn = False
        parsed_data = None
        for attempt in range(MAX_RETRIES):
            self.persistent_usage_stats["api_requests"] += 1
            self._save_persistent_stats()
            self._send_to_gui({"type": "update_persistent_stats", "payload": self.persistent_usage_stats})
            
            llm_output = self.llm_handler.generate_response(prompt_for_this_turn, self.llm_params)
            raw_response = llm_output['choices'][0]['text'].strip()
            usage_stats = llm_output.get("usage")

            logger.info(f"--- RAW API OUTPUT (ATTEMPT {attempt + 1}) ---\n{raw_response}\n---------------------------------")
            if usage_stats: logger.info(f"Token Usage: {usage_stats}")

            parsed_data, validation_error = self._parse_and_validate_response(raw_response)
            if parsed_data:
                parsed_data['original_raw_response'] = raw_response
                parsed_data['usage'] = usage_stats

                if user_message_for_this_turn:
                    self.recent_chat_log.append(f"{self.user_name}: {user_message_for_this_turn}")
                    self.pending_user_messages.clear()

                if self.file_content_for_next_turn: self.file_content_for_next_turn = ""

                is_speaking_this_turn = self._process_valid_response(parsed_data)
                response_succeeded = True
                break
            else:
                logger.warning(f"Response validation FAILED on attempt {attempt + 1}. Retrying...\n - Reason: {validation_error}")
                time.sleep(1)

        if not response_succeeded:
            log_content = f"--- API GENERATION FAILED ---\nFailed to get a valid response after {MAX_RETRIES} attempts. The input for this turn will be retried on the next cycle."
            self._send_to_gui({"type": "log_generation_failure", "payload": {"log_content": log_content}})

        if response_succeeded and parsed_data:
            self._handle_memory_consolidation(parsed_data.get('original_raw_response', ''))

        if user_message_for_this_turn and response_succeeded:
            if is_speaking_this_turn:
                self.unlock_gui_after_tts = True
            else:
                self._send_to_gui({"type": "user_input_processed"})

        if self.pending_file_read:
            feedback = self._handle_read_command(self.pending_file_read)
            self.file_content_for_next_turn += feedback
            self.force_next_turn = True
            self.pending_file_read = None

        if not self.force_next_turn and not is_speaking_this_turn:
            self.last_activity_timestamp = time.monotonic()

        self._send_to_gui({"type": "status_update", "payload": {"llm_status": "Idle"}})

    def _construct_prompt_from_state(self) -> Tuple[str, str]:
        system_content_parts = [self.system_prompt]
        for tier in ["ltm", "mtm", "stm"]:
            if self.memory[tier]:
                header = self.memory_prompt_headers.get(tier, f"#{self.agent_name}-s-{tier}-term-memories :")
                header = header.replace("{NAME}", self.agent_name)
                system_content_parts.append(f"\n{header}")
                system_content_parts.extend([f"- {entry}" for entry in self.memory[tier]])
        if self.recent_chat_log:
            chat_log_str = "\n".join(self.recent_chat_log)
            system_content_parts.append(self.prompt_templates.get('chat_log_header', '').replace('__CHAT_LOG_CONTENT__', chat_log_str))
        
        system_content_string = "\n".join(system_content_parts)

        dynamic_content_parts = []
        
        # File list injection
        try:
            file_list = [f for f in os.listdir(self.terminal_dir) if os.path.isfile(os.path.join(self.terminal_dir, f))]
            file_list_str = ', '.join(file_list) if file_list else 'none'
            file_list_template = self.prompt_templates.get('file_list_injection', '')
            if file_list_template:
                dynamic_content_parts.append(file_list_template.replace('__FILE_LIST__', file_list_str))
        except Exception as e:
            logger.error(f"Could not list terminal files for injection: {e}")

        if self.input_injector: dynamic_content_parts.append(self.input_injector)
        
        # Time injection with new format
        new_time_format = datetime.now().strftime("[time : %I:%M:%S %p][day: %d][month: %m][year: %Y]")
        dynamic_content_parts.append(self.prompt_templates.get('time_injection', '').replace('__TIME__', new_time_format))
        
        dynamic_content_parts.append(self.prompt_templates.get('user_status_injection', '').replace('__STATUS__', self.user_status))
        dynamic_content_parts.append("\n".join(filter(None, self.current_self_prompts)))
        if self.file_content_for_next_turn: dynamic_content_parts.append(self.file_content_for_next_turn)
        if self.pending_user_messages:
            combined_message = " ".join(self.pending_user_messages)
            dynamic_content_parts.append(self.prompt_templates.get('user_message_injection', '').replace('__MESSAGE__', combined_message))
        
        dynamic_content_parts.append(self.prompt_templates.get('assistant_response_start', ''))
        
        dynamic_content_string = "\n".join(filter(None, dynamic_content_parts))

        full_prompt_string = f"{system_content_string}\n{dynamic_content_string}"
        
        final_full_prompt = full_prompt_string.replace("{NAME}", self.agent_name).replace("{USER}", self.user_name)
        final_dynamic_prompt = dynamic_content_string.replace("{NAME}", self.agent_name).replace("{USER}", self.user_name)
        
        return final_full_prompt, final_dynamic_prompt

    def _parse_and_validate_response(self, raw_text: str) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:
        if not raw_text: return None, "Response was empty."
        
        if 'thinking' not in self.patterns or 'self_prompt_content' not in self.patterns:
             return None, "Internal error: regex patterns not initialized."
             
        thinking_match = self.patterns["thinking"].search(raw_text)
        if not thinking_match or not thinking_match.group(1).strip():
            return None, "Required '{thinking}' command is missing or empty."
            
        self_prompt_match = self.patterns["self_prompt_content"].search(raw_text)
        if not self_prompt_match or not self_prompt_match.group(1).strip():
            return None, f"Required '{{self-prompt-from-{self.agent_name}}}' is missing or empty."
            
        valid_blocks = self.all_recognized_commands_pattern.findall(raw_text)
        sanitized_output = "".join(valid_blocks)
        if not sanitized_output:
            return None, "Could not extract any valid command blocks."
            
        return {"sanitized_text": sanitized_output}, None

    def _process_valid_response(self, data: Dict[str, Any]) -> bool:
        sanitized_text = data["sanitized_text"]
        usage_data = data.get("usage")

        if usage_data:
            self.persistent_usage_stats["prompt_tokens"] += usage_data.get("prompt_tokens", 0)
            self.persistent_usage_stats["completion_tokens"] += usage_data.get("completion_tokens", 0)
            self.persistent_usage_stats["total_tokens"] += usage_data.get("total_tokens", 0)
            self._save_persistent_stats()
            self._send_to_gui({"type": "update_persistent_stats", "payload": self.persistent_usage_stats})
        
        new_prompts = self.patterns["all_self_prompts"].findall(sanitized_text)
        self.current_self_prompts = new_prompts if new_prompts else [self.prompt_templates.get("fallback_self_prompt", "")]
        
        log_payload = { "raw_log": data.get('original_raw_response', sanitized_text), "usage": usage_data, "tag": "output_log" }
        self._send_to_gui({"type": "new_message", "payload": log_payload})

        is_speaking_this_turn = False
        all_agent_says_texts = [match.group(1).strip() for match in self.patterns["agent_says"].finditer(sanitized_text)]

        if all_agent_says_texts:
            for text in all_agent_says_texts:
                self.recent_chat_log.append(f"{self.agent_name}: {text}")
                self._send_to_gui({"type": "new_message", "payload": {"sanitized_message": text, "chat_tag": "agent_chat"}})

            if self.tts_enabled:
                is_speaking_this_turn = True
                self.is_speaking.clear()
                self._send_to_gui({"type": "tts_playback_started"})

                def on_speech_done():
                    self._send_to_gui({"type": "tts_playback_finished"})
                    self.last_activity_timestamp = time.monotonic()
                    if self.unlock_gui_after_tts:
                        self._send_to_gui({"type": "user_input_processed"})
                        self.unlock_gui_after_tts = False
                    self.is_speaking.set()

                self.tts_queue.put((" ".join(all_agent_says_texts), self.tts_voice_id, on_speech_done))
        
        for command_match in self.patterns["agent_commands"].finditer(sanitized_text):
            self._execute_agent_command(command_match.group(1).strip())

        return is_speaking_this_turn

    def _summarize_text(self, text_to_summarize: str, summarizer_prompt_path: str, output_log_tag: str) -> str:
        if not self.llm_handler or not self.llm_handler.api_key_is_valid:
            logger.error("Summarization aborted: LLM handler not ready.")
            return ""
            
        try:
            with open(summarizer_prompt_path, 'r', encoding='utf-8') as f:
                summarizer_system_prompt = f.read()
        except FileNotFoundError:
            logger.error(f"Summarizer prompt not found at {summarizer_prompt_path}.")
            return ""

        summarizer_system_prompt = summarizer_system_prompt.replace("{NAME}", self.agent_name).replace("{USER}", self.user_name)
        
        prompt = summarizer_system_prompt.replace("__TEXT_TO_SUMMARIZE__", text_to_summarize)
        
        self._send_to_gui({
            "type": "update_full_context",
            "payload": {"full_context": prompt, "tag": "summarizer_context"}
        })
        
        self.persistent_usage_stats["api_requests"] += 1
        self._save_persistent_stats()
        self._send_to_gui({"type": "update_persistent_stats", "payload": self.persistent_usage_stats})
        
        llm_output = self.llm_handler.generate_response(prompt, self.llm_params)
        summary = llm_output['choices'][0]['text'].strip()
        
        usage_data = llm_output.get("usage")
        if usage_data:
            self.persistent_usage_stats["prompt_tokens"] += usage_data.get("prompt_tokens", 0)
            self.persistent_usage_stats["completion_tokens"] += usage_data.get("completion_tokens", 0)
            self.persistent_usage_stats["total_tokens"] += usage_data.get("total_tokens", 0)
            self._save_persistent_stats()
            self._send_to_gui({"type": "update_persistent_stats", "payload": self.persistent_usage_stats})

        self._send_to_gui({"type": "new_message", "payload": {"raw_log": summary, "usage": usage_data, "tag": output_log_tag}})
        
        return summary

    def _handle_memory_consolidation(self, turn_content: str):
        if not turn_content: return
        logger.info("--- Starting Memory Consolidation Cycle ---")
        output_log_tag = "summarizer_output"

        new_stm_entry = self._summarize_text(turn_content, self.stm_summarizer_path, output_log_tag)
        if not new_stm_entry: return

        self.memory["stm"].append(new_stm_entry)
        self._save_memory_tier("stm")
        
        stm_capacity = self.memory_capacities.get("stm", 6)
        if len(self.memory["stm"]) >= stm_capacity:
            num_to_consolidate = stm_capacity // 2 if stm_capacity >= 4 else stm_capacity
            entries_to_consolidate = self.memory["stm"][:num_to_consolidate]
            content = "\n".join([f"- {entry}" for entry in entries_to_consolidate])
            new_mtm_entry = self._summarize_text(content, self.mtm_summarizer_path, output_log_tag)

            if new_mtm_entry:
                self.memory["mtm"].append(new_mtm_entry)
                self.memory["stm"] = self.memory["stm"][num_to_consolidate:]
                self._save_memory_tier("mtm")
                self._save_memory_tier("stm")

        mtm_capacity = self.memory_capacities.get("mtm", 6)
        if len(self.memory["mtm"]) >= mtm_capacity:
            num_to_consolidate = mtm_capacity // 2 if mtm_capacity >= 4 else mtm_capacity
            entries_to_consolidate = self.memory["mtm"][:num_to_consolidate]
            content = "\n".join([f"- {entry}" for entry in entries_to_consolidate])
            new_ltm_entry = self._summarize_text(content, self.ltm_summarizer_path, output_log_tag)

            if new_ltm_entry:
                self.memory["ltm"].append(new_ltm_entry)
                self.memory["mtm"] = self.memory["mtm"][num_to_consolidate:]
                self._save_memory_tier("ltm")
                self._save_memory_tier("mtm")

        ltm_capacity = self.memory_capacities.get("ltm", 6)
        if len(self.memory["ltm"]) >= ltm_capacity:
            num_to_consolidate = ltm_capacity // 2 if ltm_capacity >= 4 else ltm_capacity
            entries_to_consolidate = self.memory["ltm"][:num_to_consolidate]
            remaining_entries = self.memory["ltm"][num_to_consolidate:]
            content = "\n".join([f"- {entry}" for entry in entries_to_consolidate])
            consolidated_ltm_entry = self._summarize_text(content, self.ltm_summarizer_path, output_log_tag)

            if consolidated_ltm_entry:
                self.memory["ltm"] = remaining_entries + [consolidated_ltm_entry]
                self._save_memory_tier("ltm")
        
        self._send_to_gui({"type": "status_update", "payload": {"memory": self.memory}})
        logger.info("--- Memory Consolidation Cycle Complete ---")

    def _save_text_to_file(self, filepath: str, content: str):
        try:
            with open(filepath, 'w', encoding='utf-8') as f: f.write(content)
            return True
        except Exception as e:
            logger.error(f"Failed to save file {os.path.basename(filepath)}: {e}", exc_info=True)
            return False

    def _execute_agent_command(self, raw_command: str):
        command = re.sub(r'\s*-\s*', '-', raw_command.strip())
        feedback = None

        read_file_match = re.fullmatch(r"read-file-([\w\.\-]+)", command, re.IGNORECASE)
        if read_file_match:
            self.pending_file_read = read_file_match.group(1)
            return

        delete_entry_match = re.fullmatch(r"([\w\.\-]+)-entry-(\d+)-delete", command, re.IGNORECASE)
        if delete_entry_match: feedback = self._handle_delete_entry_command(delete_entry_match.group(1), int(delete_entry_match.group(2)))
        
        push_update_match = re.match(r"push-update-([\w\.\-]+)\s*:\s*(.*)", command, re.DOTALL | re.IGNORECASE)
        if push_update_match: feedback = self._handle_push_command(push_update_match.group(1).strip(), push_update_match.group(2).strip())
        
        create_file_match = re.fullmatch(r"create-file-([\w\.\-]+)", command, re.IGNORECASE)
        if create_file_match: feedback = self._handle_create_file_command(create_file_match.group(1))
            
        delete_file_match = re.fullmatch(r"delete-file-([\w\.\-]+)", command, re.IGNORECASE)
        if delete_file_match: feedback = self._handle_delete_file_command(delete_file_match.group(1))

        if command.lower() == "ping-user":
            self._send_to_gui({"type": "ping_user"})
            return

        if feedback:
            self.file_content_for_next_turn += feedback
            self.force_next_turn = True

    def _get_secure_path(self, filename: str) -> Optional[str]:
        if not VALID_FILENAME_PATTERN.match(filename): return None
        return os.path.join(self.terminal_dir, os.path.basename(filename))

    def _handle_read_command(self, filename: str) -> str:
        filepath = self._get_secure_path(filename)
        if not filepath: return ""

        if not os.path.exists(filepath):
            return self.prompt_templates.get('file_read_not_found_error', '').replace('{NAME}', self.agent_name).replace('__FILENAME__', filename)
        try:
            # Read any file as text, replacing undecodable bytes.
            with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            return self.prompt_templates.get('file_read_success', '').replace('{NAME}', self.agent_name).replace('__FILENAME__', filename).replace('__CONTENT__', content)
        except Exception as e:
            logger.error(f"Failed to read file {filename}: {e}", exc_info=True)
            return self.prompt_templates.get('file_read_error', '').replace('{NAME}', self.agent_name).replace('__FILENAME__', filename)

    def _handle_push_command(self, filename: str, content_to_add: str) -> str:
        filepath = self._get_secure_path(filename)
        if not filepath: return ""
        if not os.path.exists(filepath):
            return self.prompt_templates.get('file_push_not_found_error', '').replace('__FILENAME__', filename)
        
        _, file_extension = os.path.splitext(filename)

        # Overwrite mode for non-txt files: treat them as plain text files for editing.
        if file_extension.lower() != '.txt':
            try:
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(content_to_add)
                return self.prompt_templates.get('file_push_overwrite_success', '').replace('__FILENAME__', filename)
            except Exception as e:
                logger.error(f"Failed to overwrite non-txt file {filename}: {e}", exc_info=True)
                return self.prompt_templates.get('file_read_error', '').replace('{NAME}', self.agent_name).replace('__FILENAME__', filename)

        # Append mode for .txt files
        try:
            with open(filepath, 'r+', encoding='utf-8', errors='replace') as f:
                raw_content = f.read()
                content_for_calc = raw_content.strip() if raw_content.strip() not in ["[empty]", "(empty)"] else ""
                entry_numbers = re.findall(r"\{entry-(\d+)", content_for_calc, re.IGNORECASE)
                next_entry_num = max(int(n) for n in entry_numbers) + 1 if entry_numbers else 1
                new_entry_string = f"{{entry-{next_entry_num} : {content_to_add}}}"
                
                if len(content_for_calc) + len(new_entry_string) > self.max_file_char_count:
                    return self.prompt_templates.get('file_push_capacity_error', '').replace('__FILENAME__', filename).replace('__CURRENT_CONTENT__', raw_content)

                updated_content = (content_for_calc + "\n" + new_entry_string) if content_for_calc else new_entry_string
                f.seek(0)
                f.write(updated_content)
                f.truncate()
            return self.prompt_templates.get('file_push_success', '').replace('__FILENAME__', filename).replace('__ENTRY_NUMBER__', str(next_entry_num))
        except Exception as e:
            logger.error(f"Failed to push to .txt file {filename}: {e}", exc_info=True)
            return ""


    def _handle_delete_entry_command(self, filename: str, entry_number: int) -> str:
        filepath = self._get_secure_path(filename)
        if not filepath or not os.path.exists(filepath):
            return self.prompt_templates.get('file_delete_entry_not_found', '').replace('__ENTRY_NUMBER__', str(entry_number)).replace('__FILENAME__', filename)
        try:
            with open(filepath, 'r+', encoding='utf-8') as f:
                content = f.read()
                entry_pattern = re.compile(r"\{entry-" + str(entry_number) + r"\s*:.*?\}\s*\n?", re.DOTALL | re.IGNORECASE)
                new_content, num_subs = entry_pattern.subn("", content)
                if num_subs > 0:
                    final_content = new_content.strip() or "[empty]"
                    f.seek(0)
                    f.write(final_content)
                    f.truncate()
                    return self.prompt_templates.get('file_delete_entry_success', '').replace('__ENTRY_NUMBER__', str(entry_number)).replace('__FILENAME__', filename)
                else:
                    return self.prompt_templates.get('file_delete_entry_not_found', '').replace('__ENTRY_NUMBER__', str(entry_number)).replace('__FILENAME__', filename)
        except Exception:
            return self.prompt_templates.get('file_delete_entry_error', '').replace('__FILENAME__', filename)

    def _handle_create_file_command(self, filename: str) -> str:
        filepath = self._get_secure_path(filename)
        if not filepath: return ""
        
        _, file_extension = os.path.splitext(filename)
        if file_extension.lower() not in self.allowed_file_extensions:
            return self.prompt_templates.get('file_create_invalid_extension_error', '').replace('__FILENAME__', filename).replace('__ALLOWED_EXTENSIONS__', ', '.join(self.allowed_file_extensions))

        try:
            current_files = [f for f in os.listdir(self.terminal_dir) if os.path.isfile(os.path.join(self.terminal_dir, f))]
            if len(current_files) >= self.max_terminal_files:
                return self.prompt_templates.get('file_create_capacity_error', '').replace('__FILENAME__', filename).replace('__LIMIT__', str(self.max_terminal_files)).replace('__FILE_LIST__', ', '.join(current_files))
            if os.path.exists(filepath):
                return self.prompt_templates.get('file_create_already_exists_error', '').replace('__FILENAME__', filename)
            with open(filepath, 'w', encoding='utf-8') as f: f.write("[empty]")
            return self.prompt_templates.get('file_create_success', '').replace('__FILENAME__', filename)
        except Exception:
            return self.prompt_templates.get('file_create_error', '').replace('__FILENAME__', filename)

    def _handle_delete_file_command(self, filename: str) -> str:
        filepath = self._get_secure_path(filename)
        if not filepath or not os.path.exists(filepath):
            return self.prompt_templates.get('file_delete_not_found_error', '').replace('__FILENAME__', filename)
        try:
            os.remove(filepath)
            return self.prompt_templates.get('file_delete_success', '').replace('__FILENAME__', filename)
        except Exception:
            return self.prompt_templates.get('file_delete_error', '').replace('__FILENAME__', filename)

    def _send_to_gui(self, data: Dict):
        try: self.output_q.put(data)
        except Exception as e: logger.error(f"Failed to send data to GUI: {e}")