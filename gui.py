# /wisper_project/gui.py (CORRECTED)

import tkinter as tk
from tkinter import ttk, font, messagebox, PanedWindow, Toplevel, scrolledtext
import queue
from typing import Dict, Any, Optional, List
from datetime import datetime
import re # Import regex for command detection
import webbrowser # For opening a URL

class App(tk.Tk):
    """
    The main Tkinter application window for Project Smol Agent.
    Handles all UI rendering and user input, communicating with the
    ChatManager via thread-safe queues.
    """

    def __init__(self, input_q: queue.Queue, output_q: queue.Queue, config: Dict[str, Any], title: str = "Project Smol Agent"):
        super().__init__()
        self.input_q = input_q
        self.output_q = output_q
        self.app_config = config

        # --- Regex for highlighting file commands in the raw log ---
        self.file_command_pattern = re.compile(
            r"(\{\s*(?:read-file-|create-file-|delete-file-|[\w\.\-]+-entry-\d+-delete|push-update-[\w\.\-]+:).*?\})",
            re.DOTALL | re.IGNORECASE
        )

        # --- State flags for user input handling ---
        self.is_typing = False
        self.user_input_pending = False
        self.system_prompts_editor_window: Optional[Toplevel] = None
        self.system_prompts_text_widgets: Dict[str, tk.Text] = {}
        self.summarizer_prompts_editor_window: Optional[Toplevel] = None
        self.summarizer_prompts_text_widgets: Dict[str, tk.Text] = {}


        # --- Window Configuration ---
        self.title(title)

        window_sizes_config = self.app_config.get("window_sizes", {})
        default_main_window = "1800x900"
        default_main_panes = [350, 450, 1000]
        default_right_panes = [500, 200, 500]

        main_window_size = window_sizes_config.get("main_window", default_main_window)
        self.main_pane_widths = window_sizes_config.get("main_panes", default_main_panes)
        self.right_pane_widths = window_sizes_config.get("right_panes", default_right_panes)
        self.right_pane_order = self.app_config.get("right_pane_order", ["memory_viewer", "full_context", "raw_log"])
        self.geometry(main_window_size)

        self.minsize(1200, 700)

        # --- Create Top Menu Bar ---
        self._create_top_menu()

        # --- Style Configuration ---
        self.style = ttk.Style(self)
        self.style.theme_use('clam')
        self.configure(bg="#2E2E2E")
        self.style.configure("TLabel", background="#2E2E2E", foreground="white")
        self.style.configure("TButton", background="#4A4A4A", foreground="white", relief=tk.FLAT)
        self.style.map("TButton", background=[('active', '#5A5A5A')])
        self.style.configure("TEntry", fieldbackground="#4A4A4A", foreground="white", insertbackground="white")
        self.style.configure("TCheckbutton", background="#2E2E2E", foreground="white")
        self.style.configure("TFrame", background="#2E2E2E")
        self.style.configure("TSpinbox", fieldbackground="#4A4A4A", foreground="white", arrowcolor="white", insertbackground="white")
        self.style.map('TButton', foreground=[('disabled', '#999999')])
        self.style.map('TEntry', foreground=[('disabled', '#999999')], fieldbackground=[('disabled', '#3a3a3a')])

        self.style.configure("Switch.TCheckbutton", indicatorforeground='white', indicatorbackground='#4A4A4A', padding=5)
        self.style.map('Switch.TCheckbutton',
            indicatorbackground=[('selected', '#3477eb'), ('active', '#5A5A5A')],
            background=[('active', '#2E2E2E')]
        )
        self.style.configure("Mute.TCheckbutton", indicatorforeground='white', indicatorbackground='#8B0000', padding=5)
        self.style.map('Mute.TCheckbutton',
            indicatorbackground=[('selected', '#3477eb'), ('active', '#A52A2A')],
            background=[('active', '#2E2E2E')]
        )

        self.style.configure("Danger.TButton", background="#8B0000", foreground="white")
        self.style.map("Danger.TButton", background=[('active', '#A52A2A')])

        # --- Font Configuration (from config) ---
        self.default_font = font.nametofont("TkDefaultFont")
        self.default_font.configure(size=10)
        font_sizes = self.app_config.get("font_sizes", {"chat": 11, "log": 10})
        self.chat_font = font.Font(family="Arial", size=font_sizes.get("chat", 11))
        self.log_font = font.Font(family="Courier New", size=font_sizes.get("log", 10))
        self.status_font = font.Font(family="Segoe UI", size=9) # Font for the status bar

        # --- Paned Window Layout ---
        self.main_paned_window = PanedWindow(self, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, bg="#2E2E2E")
        self.main_paned_window.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        
        # --- Create hidden text widgets to hold prompt data ---
        self.sys_prompt_text = tk.Text(self)
        self.injector_text = tk.Text(self)
        self.prompt_templates = self.app_config.get("prompt_templates", {})

        self._create_left_pane()
        self._create_center_pane()
        self._create_right_pane()
        self._create_bottom_bar()

        self.main_paned_window.add(self.left_pane, width=self.main_pane_widths[0])
        self.main_paned_window.add(self.center_pane, width=self.main_pane_widths[1])
        self.main_paned_window.add(self.right_pane, width=self.main_pane_widths[2])

        # --- Queue Processor ---
        self.after(100, self.process_incoming)

    def _create_top_menu(self):
        """Creates the main application menu bar."""
        self.menubar = tk.Menu(self)
        self.configure(menu=self.menubar)

        # --- API Key Variable ---
        self.api_key_var = tk.StringVar(value=self.app_config.get("api_key", ""))

        # --- TTS Variables ---
        self.tts_enabled_var = tk.BooleanVar(value=self.app_config.get("tts_enabled", False))
        self.selected_voice_id = tk.StringVar(value=self.app_config.get("tts_voice_id"))

        # --- API Menu ---
        api_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="API", menu=api_menu)
        api_menu.add_command(label="Set Google API Key...", command=self._open_api_key_window)

        # --- Prompts Menu ---
        prompts_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Prompts", menu=prompts_menu)
        prompts_menu.add_command(label="Main Prompt...", command=self._open_main_prompt_editor)
        prompts_menu.add_command(label="Summarizer Prompts...", command=self._open_summarizer_prompts_editor)
        prompts_menu.add_command(label="System Prompts...", command=self._open_system_prompts_editor)
        
        # --- Options Menu ---
        options_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Options", menu=options_menu)
        options_menu.add_command(label="Logs...", command=self._open_log_settings_window)
        options_menu.add_command(label="Memory Manager...", command=self._open_memory_manager_window)
        options_menu.add_command(label="Window Order...", command=self._open_window_order_window)
        
        # --- Voices Menu ---
        self.voices_menu = tk.Menu(self.menubar, tearoff=0)
        self.menubar.add_cascade(label="Voices", menu=self.voices_menu)
        self.voices_menu.add_command(label="Loading voices...", state=tk.DISABLED)

    def _create_left_pane(self):
        """Creates the left-side control panel."""
        self.left_pane = ttk.Frame(self.main_paned_window, padding=10)

        top_button_frame = ttk.Frame(self.left_pane)
        top_button_frame.pack(fill=tk.X, pady=(0, 10))

        self.save_settings_btn = ttk.Button(top_button_frame, text="Save Settings", command=self._save_all_settings)
        self.save_settings_btn.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.hard_reset_btn = ttk.Button(top_button_frame, text="Hard Reset Agent", command=self._confirm_and_hard_reset, style="Danger.TButton")
        self.hard_reset_btn.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(5,0))

        # --- Agent Auto-Turn Section ---
        ttk.Label(self.left_pane, text="Agent Auto-Turn", font=("Arial", 12, "bold")).pack(fill=tk.X, pady=(10, 5))
        auto_turn_frame = ttk.Frame(self.left_pane)
        auto_turn_frame.pack(fill=tk.X)
        self.auto_turn_var = tk.BooleanVar(value=self.app_config.get("auto_turn_enabled", False))
        self.auto_turn_switch = ttk.Checkbutton(auto_turn_frame, variable=self.auto_turn_var, style="Switch.TCheckbutton", command=self._on_auto_turn_toggle)
        self.auto_turn_switch.pack(side=tk.LEFT, pady=2)

        duration_frame = ttk.Frame(self.left_pane)
        duration_frame.pack(fill=tk.X, pady=2)
        ttk.Label(duration_frame, text="Duration (s):").pack(side=tk.LEFT)
        self.auto_turn_duration_var = tk.IntVar(value=self.app_config.get("auto_turn_duration", 60))
        ttk.Spinbox(duration_frame, from_=5, to=3600, increment=1, textvariable=self.auto_turn_duration_var, width=6).pack(side=tk.LEFT, padx=5)
        ttk.Label(duration_frame, text="(Default: 60s)").pack(side=tk.LEFT)

        # --- Generation Parameters Section (Updated for Gemini API) ---
        gen_param_header = ttk.Frame(self.left_pane)
        gen_param_header.pack(fill=tk.X, pady=(10, 5))
        ttk.Label(gen_param_header, text="Generation Parameters", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        reset_btn = ttk.Button(gen_param_header, text="Reset", command=self._reset_llm_params)
        reset_btn.pack(side=tk.RIGHT)

        llm_p = self.app_config.get("llm_params", {})
        self.param_vars = {
            "temperature": tk.DoubleVar(value=llm_p.get("temperature", 0.7)),
            "top_k": tk.IntVar(value=llm_p.get("top_k", 30)),
            "top_p": tk.DoubleVar(value=llm_p.get("top_p", 0.9)),
        }
        self._create_param_entry("Temperature", self.param_vars["temperature"], 0.0, 2.0, 0.1)
        self._create_param_entry("Top-K", self.param_vars["top_k"], 1, 100, 1)
        self._create_param_entry("Top-P", self.param_vars["top_p"], 0.0, 1.0, 0.01)

        # --- Persistent Token Usage Section ---
        token_header = ttk.Frame(self.left_pane)
        token_header.pack(fill=tk.X, pady=(15, 5))
        ttk.Label(token_header, text="Persistent Usage Stats", font=("Arial", 12, "bold")).pack(side=tk.LEFT)
        
        token_reset_frame = ttk.Frame(token_header)
        token_reset_frame.pack(side=tk.RIGHT)
        reset_tokens_btn = ttk.Button(token_reset_frame, text="Reset Tokens", command=self._reset_token_counters)
        reset_tokens_btn.pack(side=tk.TOP, fill=tk.X)
        reset_requests_btn = ttk.Button(token_reset_frame, text="Reset Requests", command=self._reset_api_requests)
        reset_requests_btn.pack(side=tk.TOP, fill=tk.X, pady=(2,0))
        
        initial_stats = self.app_config.get("persistent_usage_stats", {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0, "api_requests": 0})
        self.persistent_token_vars = {
            "prompt": tk.StringVar(value=f"{initial_stats.get('prompt_tokens', 0):,}"),
            "completion": tk.StringVar(value=f"{initial_stats.get('completion_tokens', 0):,}"),
            "total": tk.StringVar(value=f"{initial_stats.get('total_tokens', 0):,}"),
            "api_requests": tk.StringVar(value=f"{initial_stats.get('api_requests', 0):,}")
        }
        self._create_token_display("Input Tokens:", self.persistent_token_vars["prompt"])
        self._create_token_display("Output Tokens:", self.persistent_token_vars["completion"])
        self._create_token_display("Total Tokens:", self.persistent_token_vars["total"])
        self._create_token_display("API Requests:", self.persistent_token_vars["api_requests"])


        # --- Other controls Section ---
        ttk.Label(self.left_pane, text="Controls", font=("Arial", 12, "bold")).pack(fill=tk.X, pady=(10, 5))

        # --- User Status Control ---
        user_status_frame = ttk.Frame(self.left_pane)
        user_status_frame.pack(fill=tk.X, pady=5)
        ttk.Label(user_status_frame, text="User Status:").pack(side=tk.LEFT)
        self.user_status_var = tk.StringVar(value=self.app_config.get("user_status", "online"))
        status_menu = ttk.OptionMenu(user_status_frame, self.user_status_var, self.user_status_var.get(), "online", "idle", "away", "busy", "offline")
        status_menu.pack(side=tk.LEFT, padx=5)
        self.user_status_var.trace_add("write", self._update_user_status_live)

        # --- TTS Control ---
        tts_control_frame = ttk.Frame(self.left_pane)
        tts_control_frame.pack(fill=tk.X, pady=5)
        self.tts_switch = ttk.Checkbutton(tts_control_frame, variable=self.tts_enabled_var, style="Mute.TCheckbutton", command=self._on_tts_toggle)
        self.tts_switch.pack(side=tk.LEFT)
        
        # --- Memory Manager and Log settings variables ---
        mem_caps = self.app_config.get("memory_capacities", {"stm": 6, "mtm": 6, "ltm": 6})
        self.memory_capacity_vars = {
            "stm": tk.IntVar(value=mem_caps.get("stm", 6)),
            "mtm": tk.IntVar(value=mem_caps.get("mtm", 6)),
            "ltm": tk.IntVar(value=mem_caps.get("ltm", 6)),
        }
        self.chat_log_length_var = tk.IntVar(value=self.app_config.get("chat_log_length", 10))
        self.max_file_char_count_var = tk.IntVar(value=self.app_config.get("max_file_char_count", 500))
        self.max_terminal_files_var = tk.IntVar(value=self.app_config.get("max_terminal_files", 10))
        
        # --- Agent and User Name variables ---
        self.agent_name_var = tk.StringVar(value=self.app_config.get("agent_name", "Agent"))
        self.user_name_var = tk.StringVar(value=self.app_config.get("user_name", "User"))
        self.hard_reset_btn.config(command=self._confirm_and_hard_reset)

        # --- Font settings variables ---
        self.chat_font_size_var = tk.IntVar(value=self.chat_font.cget("size"))
        self.log_font_size_var = tk.IntVar(value=self.log_font.cget("size"))
        
        # --- Set Initial Button Labels ---
        self._update_auto_turn_label()
        self._update_tts_label()


    def _create_param_entry(self, label_text, var, from_, to, increment):
        frame = ttk.Frame(self.left_pane)
        frame.pack(fill=tk.X, pady=2)
        ttk.Label(frame, text=label_text, width=15).pack(side=tk.LEFT)
        ttk.Spinbox(frame, from_=from_, to=to, increment=increment, textvariable=var, width=10, wrap=True).pack(side=tk.LEFT, padx=5)

    def _create_token_display(self, label_text: str, var: tk.StringVar):
        """Helper to create a label and a display for token counts."""
        frame = ttk.Frame(self.left_pane)
        frame.pack(fill=tk.X, pady=1)
        ttk.Label(frame, text=label_text, width=15, anchor="w").pack(side=tk.LEFT)
        ttk.Label(frame, textvariable=var, width=12, anchor="e", font=("Courier New", 10)).pack(side=tk.RIGHT, padx=5)

    def _reset_token_counters(self):
        """Sends a command to the ChatManager to reset persistent token stats."""
        if messagebox.askyesno("Confirm Reset", "Are you sure you want to reset the persistent token counters? This cannot be undone."):
            self._send_to_manager("reset_persistent_stats", None)

    def _reset_api_requests(self):
        """Sends a command to the ChatManager to reset persistent API request count."""
        if messagebox.askyesno("Confirm Reset", "Are you sure you want to reset the persistent API request counter? This cannot be undone."):
            self._send_to_manager("reset_api_requests", None)

    def _create_center_pane(self):
        self.center_pane = ttk.Frame(self.main_paned_window, padding=5)
        ttk.Label(self.center_pane, text="Sanitized Chat", font=("Arial", 12, "bold")).pack(fill=tk.X)
        self.chat_text = tk.Text(self.center_pane, wrap=tk.WORD, state=tk.DISABLED, font=self.chat_font, bg="#1E1E1E", fg="white")
        self.chat_text.pack(fill=tk.BOTH, expand=True, pady=(5,0))
        self.chat_text.tag_config("user_chat", foreground="#FF8E8E")
        self.chat_text.tag_config("agent_chat", foreground="#8EB8FF")
        self.chat_text.tag_config("info", foreground="#AAAAAA", font=(self.chat_font.cget("family"), self.chat_font.cget("size"), "italic"))

    def _create_right_pane(self):
        self.right_pane = PanedWindow(self.main_paned_window, orient=tk.HORIZONTAL, sashrelief=tk.RAISED, bg="#2E2E2E")
        self.right_pane_widgets = {}

        # --- Create Memory Viewer Pane ---
        self.stm_log_frame = ttk.Frame(self.right_pane, padding=5)
        ttk.Label(self.stm_log_frame, text="Tiered Memory Viewer", font=("Arial", 12, "bold")).pack(fill=tk.X)
        self.stm_log_text = tk.Text(self.stm_log_frame, wrap=tk.WORD, state=tk.DISABLED, font=self.log_font, bg="#1E1E1E", fg="#B0E0E6")
        self.stm_log_text.pack(fill=tk.BOTH, expand=True, pady=(5,0))
        self.stm_log_text.tag_config("stm_header", foreground="#87CEFA", font=(self.log_font.cget("family"), self.log_font.cget("size"), "bold"))
        self.stm_log_text.tag_config("mtm_header", foreground="#FFD700", font=(self.log_font.cget("family"), self.log_font.cget("size"), "bold"))
        self.stm_log_text.tag_config("ltm_header", foreground="#FF6347", font=(self.log_font.cget("family"), self.log_font.cget("size"), "bold"))
        self.stm_log_text.tag_config("memory_entry", foreground="#E0FFFF")
        self.stm_log_text.tag_config("info", foreground="#AAAAAA", font=(self.log_font.cget("family"), self.log_font.cget("size"), "italic"))
        self.right_pane_widgets["memory_viewer"] = self.stm_log_frame

        # --- Create Full Context Pane ---
        self.full_context_frame = ttk.Frame(self.right_pane, padding=5)
        ttk.Label(self.full_context_frame, text="Full Context", font=("Arial", 12, "bold")).pack(fill=tk.X)
        self.full_context_text = tk.Text(self.full_context_frame, wrap=tk.WORD, state=tk.DISABLED, font=self.log_font, bg="#1E1E1E", fg="#DDA0DD")
        self.full_context_text.pack(fill=tk.BOTH, expand=True, pady=(5,0))
        self.full_context_text.tag_config("info", foreground="#AAAAAA", font=(self.log_font.cget("family"), self.log_font.cget("size"), "italic"))
        self.full_context_text.tag_config("summarizer_context", foreground="#FFA500") 
        self.right_pane_widgets["full_context"] = self.full_context_frame

        # --- Create Raw Log Pane ---
        self.raw_log_frame = ttk.Frame(self.right_pane, padding=5)
        ttk.Label(self.raw_log_frame, text="Raw LLM Log", font=("Arial", 12, "bold")).pack(fill=tk.X)
        self.log_text = tk.Text(self.raw_log_frame, wrap=tk.WORD, state=tk.DISABLED, font=self.log_font, bg="#1E1E1E", fg="#CCCCCC")
        self.log_text.pack(fill=tk.BOTH, expand=True, pady=(5,0))
        self.log_text.tag_config("input_log", foreground="#FF8E8E")
        self.log_text.tag_config("output_log", foreground="#8EB8FF")
        self.log_text.tag_config("error_log", foreground="#FFFF00")
        self.log_text.tag_config("summarizer_input", foreground="#FFA500")
        self.log_text.tag_config("summarizer_output", foreground="#FFFF00")
        self.log_text.tag_config("file_command_log", foreground="#4CAF50", font=(self.log_font.cget("family"), self.log_font.cget("size"), "bold"))
        self.right_pane_widgets["raw_log"] = self.raw_log_frame

        # --- Add panes to window in specified order ---
        self._reorder_right_panes()

    def _reorder_right_panes(self):
        """Forgets and re-adds the right-hand panes according to the self.right_pane_order list."""
        for pane in self.right_pane.winfo_children():
            self.right_pane.forget(pane)

        pane_widths = self.right_pane_widths
        for i, pane_key in enumerate(self.right_pane_order):
            if pane_key in self.right_pane_widgets:
                width = pane_widths[i] if i < len(pane_widths) else 200
                self.right_pane.add(self.right_pane_widgets[pane_key], width=width)

    def _create_bottom_bar(self):
        """Creates the bottom bar with input entry, send button, and status bar."""
        bottom_frame = ttk.Frame(self, padding=5)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)

        self.input_entry = ttk.Entry(bottom_frame, font=self.chat_font)
        self.input_entry.pack(fill=tk.X, expand=True, side=tk.LEFT, padx=(0, 5))
        self.input_entry.bind("<Return>", self.send_message)
        self.input_entry.bind("<KeyRelease>", self._handle_typing_event)

        self.send_button = ttk.Button(bottom_frame, text="Send", command=self.send_message)
        self.send_button.pack(side=tk.LEFT)

        # CORRECTED: Use a tk.Text widget for the status bar to support colored text
        self.status_bar = tk.Text(
            self, height=1,
            font=self.status_font,
            bg="#252526",  # A slightly different shade for the bar
            fg="white",
            relief=tk.SUNKEN,
            bd=1,
            padx=4,
            pady=2,
            state=tk.DISABLED,
            wrap=tk.NONE # Prevent line wrapping
        )
        self.status_bar.pack(side=tk.BOTTOM, fill=tk.X)

        self.status_data = {"llm_status": "Idle", "turn_timer": "N/A", "info": "Ready", "api_status": "Initializing..."}
        # Initial status bar update
        self._update_status_bar()


    # --- POPUP WINDOWS ---
    def _open_api_key_window(self):
        win = Toplevel(self)
        win.title("Set Google Gemini API Key")
        win.configure(bg="#2E2E2E")
        win.geometry("500x200")
        win.resizable(False, False)

        main_frame = ttk.Frame(win, padding=20)
        main_frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(main_frame, text="Enter your Google Gemini API key below.").pack(anchor="w")

        entry_frame = ttk.Frame(main_frame)
        entry_frame.pack(fill=tk.X, pady=10)
        
        api_entry = ttk.Entry(entry_frame, textvariable=self.api_key_var, show="*")
        api_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)

        show_var = tk.BooleanVar()
        def toggle_visibility():
            api_entry.config(show="" if show_var.get() else "*")
        
        show_check = ttk.Checkbutton(entry_frame, text="Show", variable=show_var, command=toggle_visibility)
        show_check.pack(side=tk.LEFT, padx=5)

        def open_link(event):
            webbrowser.open_new(r"https://aistudio.google.com/app/apikey")

        link_label = ttk.Label(main_frame, text="Get an API key from Google AI Studio", foreground="#3477eb", cursor="hand2")
        link_label.pack(anchor="w", pady=5)
        link_label.bind("<Button-1>", open_link)

        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(10, 0))

        def on_save():
            new_key = self.api_key_var.get().strip()
            self._send_to_manager("update_api_key", new_key)
            self.add_chat_message("System: ", "API Key updated. The system will now use the new key.", "info")
            win.destroy()

        save_btn = ttk.Button(button_frame, text="Save & Apply", command=on_save)
        save_btn.pack(side=tk.RIGHT)
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=win.destroy)
        cancel_btn.pack(side=tk.RIGHT, padx=5)

        win.transient(self)
        win.grab_set()
        self.wait_window(win)

    def _open_main_prompt_editor(self):
        editor = Toplevel(self)
        editor.title("Main Prompt Editor")
        editor.geometry("800x600")
        editor.configure(bg="#2E2E2E")

        top_frame = ttk.Frame(editor, padding=(10, 10, 10, 0))
        top_frame.pack(fill=tk.X)
        top_frame.columnconfigure(1, weight=1)

        ttk.Label(top_frame, text="Agent Name ({NAME}):").grid(row=0, column=0, sticky="w", padx=(0, 5), pady=2)
        agent_name_entry = ttk.Entry(top_frame, textvariable=self.agent_name_var)
        agent_name_entry.grid(row=0, column=1, sticky="ew")

        ttk.Label(top_frame, text="User Name ({USER}):").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=2)
        user_name_entry = ttk.Entry(top_frame, textvariable=self.user_name_var)
        user_name_entry.grid(row=1, column=1, sticky="ew", pady=(0, 5))
        
        text_widget = tk.Text(editor, wrap=tk.WORD, bg="#1E1E1E", fg="white", insertbackground="white", undo=True)
        text_widget.pack(fill=tk.BOTH, expand=True, padx=10, pady=(5, 5))
        text_widget.insert("1.0", self.sys_prompt_text.get("1.0", tk.END))
        
        button_frame = ttk.Frame(editor)
        button_frame.pack(fill=tk.X, padx=10, pady=(0, 10))
        
        def on_save():
            new_content = text_widget.get("1.0", tk.END).strip()
            self.sys_prompt_text.delete("1.0", tk.END)
            self.sys_prompt_text.insert("1.0", new_content)
            self._send_to_manager("save_main_prompt", {"system_prompt": new_content})
            self.hard_reset_btn.config(text=f"Hard Reset {self.agent_name_var.get()}")
            editor.destroy()

        save_btn = ttk.Button(button_frame, text="Save & Close", command=on_save)
        save_btn.pack(side=tk.RIGHT, padx=5)
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=editor.destroy)
        cancel_btn.pack(side=tk.RIGHT)
        
        editor.transient(self)
        editor.grab_set()
        self.wait_window(editor)
    
    def _open_summarizer_prompts_editor(self):
        if self.summarizer_prompts_editor_window and self.summarizer_prompts_editor_window.winfo_exists():
            self.summarizer_prompts_editor_window.lift()
            return

        self.summarizer_prompts_editor_window = Toplevel(self)
        self.summarizer_prompts_editor_window.title("Memory Summarizer Prompts Editor")
        self.summarizer_prompts_editor_window.geometry("900x700")
        self.summarizer_prompts_editor_window.configure(bg="#2E2E2E")

        self._send_to_manager("get_summarizer_prompts", None)

        loading_label = ttk.Label(self.summarizer_prompts_editor_window, text="Loading summarizer prompts...", font=("Arial", 14))
        loading_label.pack(pady=50)

        self.summarizer_prompts_editor_window.transient(self)
        self.summarizer_prompts_editor_window.grab_set()

    def _populate_summarizer_prompts_editor(self, prompt_data: Dict[str, str]):
        if not self.summarizer_prompts_editor_window or not self.summarizer_prompts_editor_window.winfo_exists():
            return

        for widget in self.summarizer_prompts_editor_window.winfo_children():
            widget.destroy()

        self.summarizer_prompts_text_widgets.clear()
        main_frame = ttk.Frame(self.summarizer_prompts_editor_window, padding=10)
        main_frame.pack(fill=tk.BOTH, expand=True)

        def add_editor(parent, key, title, content):
            ttk.Label(parent, text=title, font=("Arial", 11, "bold")).pack(fill=tk.X, pady=(10, 2))
            text_widget = tk.Text(parent, height=8, wrap=tk.WORD, bg="#1E1E1E", fg="white", insertbackground="white", undo=True)
            text_widget.pack(fill=tk.BOTH, expand=True)
            text_widget.insert("1.0", content)
            self.summarizer_prompts_text_widgets[key] = text_widget

        add_editor(main_frame, "stm", "Short-Term Memory (STM) Summarizer Prompt", prompt_data.get("stm", ""))
        add_editor(main_frame, "mtm", "Medium-Term Memory (MTM) Summarizer Prompt", prompt_data.get("mtm", ""))
        add_editor(main_frame, "ltm", "Long-Term Memory (LTM) Summarizer Prompt", prompt_data.get("ltm", ""))
        
        ttk.Label(main_frame, text="Note: These prompts can use {NAME} and {USER} variables.", font=("Arial", 9, "italic")).pack(pady=5)

        button_frame = ttk.Frame(self.summarizer_prompts_editor_window, padding=(0, 0, 10, 10))
        button_frame.pack(fill=tk.X, side=tk.BOTTOM)
        
        def on_save():
            payload = {key: widget.get("1.0", tk.END).strip() for key, widget in self.summarizer_prompts_text_widgets.items()}
            self._send_to_manager("save_summarizer_prompts", payload)
            self.summarizer_prompts_editor_window.destroy()

        save_btn = ttk.Button(button_frame, text="Save & Close", command=on_save)
        save_btn.pack(side=tk.RIGHT, padx=5)
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.summarizer_prompts_editor_window.destroy)
        cancel_btn.pack(side=tk.RIGHT)

    def _open_system_prompts_editor(self):
        if self.system_prompts_editor_window and self.system_prompts_editor_window.winfo_exists():
            self.system_prompts_editor_window.lift()
            return
            
        self.system_prompts_editor_window = Toplevel(self)
        self.system_prompts_editor_window.title("System & Template Prompts Editor")
        self.system_prompts_editor_window.geometry("900x700")
        self.system_prompts_editor_window.configure(bg="#2E2E2E")
        
        self._send_to_manager("get_all_prompts", None)

        loading_label = ttk.Label(self.system_prompts_editor_window, text="Loading prompts...", font=("Arial", 14))
        loading_label.pack(pady=50)

        self.system_prompts_editor_window.transient(self)
        self.system_prompts_editor_window.grab_set()
        
    def _populate_system_prompts_editor(self, prompt_data: Dict[str, Any]):
        if not self.system_prompts_editor_window or not self.system_prompts_editor_window.winfo_exists():
            return
        
        for widget in self.system_prompts_editor_window.winfo_children():
            widget.destroy()

        self.system_prompts_text_widgets.clear()
        
        main_frame = ttk.Frame(self.system_prompts_editor_window)
        main_frame.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(main_frame, bg="#2E2E2E", highlightthickness=0)
        scrollbar = ttk.Scrollbar(main_frame, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        canvas.pack(side="left", fill="both", expand=True, padx=5, pady=5)
        scrollbar.pack(side="right", fill="y")
        
        def _on_mousewheel(event):
            if event.num == 5 or event.delta < 0:
                canvas.yview_scroll(1, "units")
            elif event.num == 4 or event.delta > 0:
                canvas.yview_scroll(-1, "units")
        
        def _bind_mousewheel_recursively(widget):
            widget.bind('<MouseWheel>', _on_mousewheel)
            widget.bind('<Button-4>', _on_mousewheel)
            widget.bind('<Button-5>', _on_mousewheel)
            for child in widget.winfo_children():
                _bind_mousewheel_recursively(child)

        _bind_mousewheel_recursively(scrollable_frame)
        canvas.bind('<MouseWheel>', _on_mousewheel)

        def add_prompt_editor(parent, key, value, height):
            ttk.Label(parent, text=f"{key}:", font=("Arial", 10, "bold")).pack(fill=tk.X, padx=5, pady=(10, 2))
            text_widget = tk.Text(parent, height=height, wrap=tk.WORD, bg="#1E1E1E", fg="white", insertbackground="white", undo=True)
            text_widget.pack(fill=tk.X, padx=5, expand=True)
            text_widget.insert("1.0", value)
            self.system_prompts_text_widgets[key] = text_widget
        
        add_prompt_editor(scrollable_frame, "input_injector", prompt_data.get("input_injector", ""), 4)

        templates = prompt_data.get("prompt_templates", {})
        for key, value in sorted(templates.items()):
            add_prompt_editor(scrollable_frame, key, value, 3)
            
        button_frame = ttk.Frame(self.system_prompts_editor_window)
        button_frame.pack(fill=tk.X, padx=10, pady=10)
        
        def on_save():
            if "input_injector" in self.system_prompts_text_widgets:
                self.injector_text.delete("1.0", tk.END)
                self.injector_text.insert("1.0", self.system_prompts_text_widgets["input_injector"].get("1.0", tk.END).strip())
            
            updated_templates = {}
            for key, widget in self.system_prompts_text_widgets.items():
                if key != "input_injector":
                    updated_templates[key] = widget.get("1.0", tk.END).strip()
            self.prompt_templates = updated_templates
            
            payload_to_save = {
                "input_injector": self.injector_text.get("1.0", tk.END).strip(),
                "prompt_templates": self.prompt_templates
            }
            
            self._send_to_manager("save_system_prompts", payload_to_save)
            self.system_prompts_editor_window.destroy()

        save_btn = ttk.Button(button_frame, text="Save & Close", command=on_save)
        save_btn.pack(side=tk.RIGHT, padx=5)
        cancel_btn = ttk.Button(button_frame, text="Cancel", command=self.system_prompts_editor_window.destroy)
        cancel_btn.pack(side=tk.RIGHT)
        
        _bind_mousewheel_recursively(scrollable_frame)

    def _open_log_settings_window(self):
        win = Toplevel(self)
        win.title("Log Settings")
        win.configure(bg="#2E2E2E")
        
        main_frame = ttk.Frame(win, padding=20)
        main_frame.pack()
        
        font_frame = ttk.Frame(main_frame)
        font_frame.pack(fill=tk.X, pady=5)
        
        ttk.Label(font_frame, text="Chat Font Size:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        ttk.Spinbox(font_frame, from_=8, to=20, increment=1, textvariable=self.chat_font_size_var, width=5).grid(row=0, column=1, padx=5)

        ttk.Label(font_frame, text="Log Font Size:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        ttk.Spinbox(font_frame, from_=8, to=20, increment=1, textvariable=self.log_font_size_var, width=5).grid(row=1, column=1, padx=5)
        
        def on_apply():
            self._apply_font_settings()
            self.add_chat_message("System: ", "Font sizes updated. Click 'Save Settings' to persist.", "info")
            win.destroy()
            
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        apply_btn = ttk.Button(button_frame, text="Apply & Close", command=on_apply)
        apply_btn.pack(side=tk.RIGHT)

        win.transient(self)
        win.grab_set()

    def _open_memory_manager_window(self):
        win = Toplevel(self)
        win.title("Memory & Context Manager")
        win.configure(bg="#2E2E2E")

        main_frame = ttk.Frame(win, padding=20)
        main_frame.pack()
        
        ttk.Label(main_frame, text="Memory Capacities", font=("Arial", 11, "bold")).pack(fill=tk.X, pady=(0, 5))
        
        def add_spinbox(parent, label_text, var, from_val=1, to_val=100):
            frame = ttk.Frame(parent)
            frame.pack(fill=tk.X, pady=2)
            ttk.Label(frame, text=f"{label_text}:", width=25).pack(side=tk.LEFT)
            ttk.Spinbox(frame, from_=from_val, to=to_val, increment=1, textvariable=var, width=6).pack(side=tk.LEFT, padx=5)
        
        add_spinbox(main_frame, "Short-Term Memory (STM) Size", self.memory_capacity_vars["stm"])
        add_spinbox(main_frame, "Medium-Term Memory (MTM) Size", self.memory_capacity_vars["mtm"])
        add_spinbox(main_frame, "Long-Term Memory (LTM) Size", self.memory_capacity_vars["ltm"])
        
        ttk.Separator(main_frame, orient=tk.HORIZONTAL).pack(fill=tk.X, pady=10)
        ttk.Label(main_frame, text="Context & File Settings", font=("Arial", 11, "bold")).pack(fill=tk.X, pady=(0, 5))

        add_spinbox(main_frame, "Chat Log Messages in Context", self.chat_log_length_var)
        add_spinbox(main_frame, "Max File Character Count", self.max_file_char_count_var, from_val=100, to_val=5000)
        add_spinbox(main_frame, "Max Terminal Files", self.max_terminal_files_var, from_val=1, to_val=50)


        def on_save():
            self.add_chat_message("System: ", "Memory/Context settings updated. Click 'Save Settings' to persist.", "info")
            win.destroy()
            
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(fill=tk.X, pady=(15, 0))
        save_btn = ttk.Button(button_frame, text="Save & Close", command=on_save)
        save_btn.pack(side=tk.RIGHT)

        win.transient(self)
        win.grab_set()

    def _open_window_order_window(self):
        win = Toplevel(self)
        win.title("Right Pane Order")
        win.configure(bg="#2E2E2E")
        
        main_frame = ttk.Frame(win, padding=15)
        main_frame.pack(fill=tk.BOTH, expand=True)

        listbox_frame = ttk.Frame(main_frame)
        listbox_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        
        ttk.Label(listbox_frame, text="Set order (top to bottom is left to right):").pack(anchor="w")
        
        listbox = tk.Listbox(listbox_frame, height=5, bg="#4A4A4A", fg="white", selectbackground="#3477eb")
        listbox.pack(fill=tk.X, expand=True, pady=5)
        
        pane_map = {
            "memory_viewer": "Tiered Memory Viewer",
            "full_context": "Full Context",
            "raw_log": "Raw LLM Log"
        }
        
        for pane_key in self.right_pane_order:
            listbox.insert(tk.END, pane_map.get(pane_key, pane_key))
            
        button_frame = ttk.Frame(main_frame)
        button_frame.pack(side=tk.LEFT, fill=tk.Y, padx=10)

        def move(direction):
            selected_indices = listbox.curselection()
            if not selected_indices: return
            idx = selected_indices[0]
            
            if direction == "up" and idx > 0: new_idx = idx - 1
            elif direction == "down" and idx < listbox.size() - 1: new_idx = idx + 1
            else: return
                
            item = listbox.get(idx)
            listbox.delete(idx)
            listbox.insert(new_idx, item)
            listbox.selection_set(new_idx)
            
        up_btn = ttk.Button(button_frame, text="▲ Up", command=lambda: move("up"))
        up_btn.pack(pady=2)
        down_btn = ttk.Button(button_frame, text="▼ Down", command=lambda: move("down"))
        down_btn.pack(pady=2)
        
        def on_apply():
            reverse_pane_map = {v: k for k, v in pane_map.items()}
            new_order = [reverse_pane_map.get(listbox.get(i)) for i in range(listbox.size())]
            
            self.right_pane_order = [key for key in new_order if key]
            self._reorder_right_panes()
            
            self.add_chat_message("System: ", "Pane order updated. Click 'Save Settings' to persist.", "info")
            win.destroy()
            
        apply_btn = ttk.Button(main_frame, text="Apply & Reorder", command=on_apply)
        apply_btn.pack(side=tk.BOTTOM, fill=tk.X, pady=(10, 0))
        
        win.transient(self)
        win.grab_set()

    def _reset_llm_params(self):
        # Updated defaults for Gemini
        defaults = {"temperature": 0.7, "top_k": 30, "top_p": 0.9}
        for key, value in defaults.items():
            if key in self.param_vars:
                self.param_vars[key].set(value)
        self.add_chat_message("System: ", "LLM parameters reset to default. Click 'Save Settings' to apply.", "info")

    def _apply_font_settings(self):
        chat_size = self.chat_font_size_var.get()
        log_size = self.log_font_size_var.get()
        self.chat_font.configure(size=chat_size)
        self.log_font.configure(size=log_size)
        self.chat_text.tag_config("info", font=(self.chat_font.cget("family"), chat_size, "italic"))
        self.stm_log_text.tag_config("info", font=(self.log_font.cget("family"), log_size, "italic"))
        self.full_context_text.tag_config("info", font=(self.log_font.cget("family"), log_size, "italic"))

    def _update_auto_turn_label(self):
        is_enabled = self.auto_turn_var.get()
        self.auto_turn_switch.config(text=f"Auto-Turn is {'Enabled' if is_enabled else 'Disabled'}")

    def _on_auto_turn_toggle(self):
        self._update_auto_turn_label()
        self._update_auto_turn_state()

    def _update_auto_turn_state(self):
        is_enabled = self.auto_turn_var.get()
        self._send_to_manager("update_auto_turn_state", is_enabled)
        
    def _update_tts_label(self):
        is_enabled = self.tts_enabled_var.get()
        self.tts_switch.config(text=f"Voice is {'Enabled' if is_enabled else 'Disabled'}")

    def _on_tts_toggle(self):
        self._update_tts_label()
        self._toggle_tts()

    def _toggle_tts(self):
        self._send_to_manager("update_tts_state", self.tts_enabled_var.get())

    def _select_voice(self):
        self._send_to_manager("update_tts_voice", self.selected_voice_id.get())

    def _update_user_status_live(self, *args):
        new_status = self.user_status_var.get()
        self._send_to_manager("update_user_status", new_status)

    def _handle_typing_event(self, event=None):
        current_text = self.input_entry.get()
        currently_typing = len(current_text) > 0

        if currently_typing != self.is_typing:
            self.is_typing = currently_typing
            self._send_to_manager("user_typing_status", self.is_typing)

    def _confirm_and_hard_reset(self):
        agent_name = self.agent_name_var.get()
        if messagebox.askyesno(
            f"Confirm Hard Reset for {agent_name}",
            f"This will wipe {agent_name}'s tiered memory (STM, MTM, LTM), clear chat history, and wipe all files in the /terminal/ directory to be empty.\n\n"
            "This action does NOT reset your saved prompts, settings, or API key. It only clears the agent's state.\n\n"
            "It will also disable auto-turn. Are you sure you want to proceed?"
        ):
            self._send_to_manager("hard_reset", None)

    def _save_all_settings(self, event=None, is_quitting=False):
        self.update_idletasks()
        if not is_quitting:
            self._apply_font_settings()

        current_pane_widths = []
        for pane_key in self.right_pane_order:
             if pane_key in self.right_pane_widgets:
                current_pane_widths.append(self.right_pane_widgets[pane_key].winfo_width())
        self.right_pane_widths = current_pane_widths if current_pane_widths else self.right_pane_widths

        window_sizes = {
            "main_window": f"{self.winfo_width()}x{self.winfo_height()}",
            "main_panes": [
                self.left_pane.winfo_width(),
                self.center_pane.winfo_width(),
                self.right_pane.winfo_width()
            ],
            "right_panes": self.right_pane_widths
        }

        settings = {
            "window_sizes": window_sizes,
            "right_pane_order": self.right_pane_order,
            "llm_params": {key: var.get() for key, var in self.param_vars.items()},
            "user_status": self.user_status_var.get(),
            "auto_turn_enabled": self.auto_turn_var.get(),
            "auto_turn_duration": self.auto_turn_duration_var.get(),
            "chat_log_length": self.chat_log_length_var.get(),
            "max_file_char_count": self.max_file_char_count_var.get(),
            "max_terminal_files": self.max_terminal_files_var.get(),
            "agent_name": self.agent_name_var.get(),
            "user_name": self.user_name_var.get(),
            "memory_capacities": {key: var.get() for key, var in self.memory_capacity_vars.items()},
            "font_sizes": {
                "chat": self.chat_font_size_var.get(),
                "log": self.log_font_size_var.get()
            },
            "tts_enabled": self.tts_enabled_var.get(),
            "tts_voice_id": self.selected_voice_id.get(),
            "api_key": self.api_key_var.get()
        }
        self._send_to_manager("save_all_settings", settings)

        if not is_quitting:
            self.add_chat_message("System: ", "Settings and window layout saved.", "info")

    def send_message(self, event=None):
        if self.user_input_pending:
            self.bell()
            return

        message = self.input_entry.get().strip()
        if message:
            self.input_entry.delete(0, tk.END)
            self._handle_typing_event()

            self._send_to_manager("user_message", message)
            self.add_chat_message(f"{self.user_name_var.get()}: ", message, "user_chat")

            self.user_input_pending = True
            self.input_entry.config(state=tk.DISABLED)
            self.send_button.config(state=tk.DISABLED)
            self.status_data["info"] = "Awaiting response..."
            self._update_status_bar()

    def add_chat_message(self, prefix: str, message: str, tag: str):
        self.chat_text.config(state=tk.NORMAL)
        self.chat_text.insert(tk.END, f"{prefix}{message}\n\n", tag)
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)

    def add_log_message(self, log_data: str, tag: Optional[str] = None):
        self.log_text.config(state=tk.NORMAL)
        base_tag = tag or "output_log"

        parts = self.file_command_pattern.split(log_data)

        for i, part in enumerate(parts):
            if not part: continue
            current_tag = "file_command_log" if i % 2 != 0 else base_tag
            self.log_text.insert(tk.END, part, current_tag)

        self.log_text.insert(tk.END, "\n" + "-"*80 + "\n")
        self.log_text.config(state=tk.DISABLED)
        self.log_text.see(tk.END)

    def update_memory_log(self, memory_data: Dict[str, List[str]]):
        self.stm_log_text.config(state=tk.NORMAL)
        self.stm_log_text.delete("1.0", tk.END)

        if not any(memory_data.values()):
            self.stm_log_text.insert(tk.END, "[All memory tiers are empty]", "info")
        else:
            if memory_data.get("ltm"):
                self.stm_log_text.insert(tk.END, "Long-Term Memory\n", "ltm_header")
                for entry in memory_data["ltm"]: self.stm_log_text.insert(tk.END, f"- {entry}\n", "memory_entry")
                self.stm_log_text.insert(tk.END, "\n")
            
            if memory_data.get("mtm"):
                self.stm_log_text.insert(tk.END, "Medium-Term Memory\n", "mtm_header")
                for entry in memory_data["mtm"]: self.stm_log_text.insert(tk.END, f"- {entry}\n", "memory_entry")
                self.stm_log_text.insert(tk.END, "\n")
            
            if memory_data.get("stm"):
                self.stm_log_text.insert(tk.END, "Short-Term Memory\n", "stm_header")
                for entry in memory_data["stm"]: self.stm_log_text.insert(tk.END, f"- {entry}\n", "memory_entry")
        
        self.stm_log_text.config(state=tk.DISABLED)
        self.stm_log_text.see(tk.END)

    def update_full_context(self, full_context_content: str, tag: Optional[str] = None):
        self.full_context_text.config(state=tk.NORMAL)
        self.full_context_text.delete("1.0", tk.END)

        if full_context_content:
            self.full_context_text.insert(tk.END, full_context_content, tag)
        else:
            self.full_context_text.insert(tk.END, "[Waiting for first turn to generate context...]", "info")

        self.full_context_text.config(state=tk.DISABLED)
        self.full_context_text.see(tk.END)

    def _populate_voices_menu(self, voices: List[Dict[str, str]]):
        self.voices_menu.delete(0, tk.END)
        if not voices:
            self.voices_menu.add_command(label="No TTS voices found", state=tk.DISABLED)
            return

        for voice in voices:
            self.voices_menu.add_radiobutton(
                label=voice['name'],
                value=voice['id'],
                variable=self.selected_voice_id,
                command=self._select_voice
            )

        # Check if the saved voice ID is still valid
        saved_id = self.selected_voice_id.get()
        if not any(v['id'] == saved_id for v in voices):
            # If not, select the first voice in the list as a fallback
            if voices:
                self.selected_voice_id.set(voices[0]['id'])
                self._select_voice()
            else:
                 self.selected_voice_id.set("")

    def _update_status_bar(self):
        """CORRECTED: Updates the status bar using tk.Text methods."""
        api_status = self.status_data.get("api_status", "Unknown")
        llm_status = self.status_data.get("llm_status", "Idle")
        user_status = self.user_status_var.get()
        turn_timer = self.status_data.get("turn_timer", "N/A")
        info = self.status_data.get("info", "")
        auto_turn_status = "ON" if self.auto_turn_var.get() else "OFF"
        
        # Determine color for API status
        if api_status == "Valid":
            api_status_color = "#4CAF50" # Green
        elif api_status == "Invalid":
            api_status_color = "#F44336" # Red
        else: # Initializing or Unknown
            api_status_color = "#FFC107" # Amber

        # Define tags for colors
        self.status_bar.tag_configure("api_ok", foreground=api_status_color)
        self.status_bar.tag_configure("default", foreground="white")

        # Build the status string with parts and their corresponding tags
        status_parts = [
            (" API: ", "default"), (f"{api_status}", "api_ok"), (" | ", "default"),
            (f"LLM: {llm_status}", "default"), (" | ", "default"),
            (f"User: {user_status}", "default"), (" | ", "default"),
            (f"Auto-Turn: {auto_turn_status}", "default"), (" | ", "default"),
            (f"{turn_timer}", "default"), (" | ", "default"),
            (f"{info}", "default")
        ]
        
        # Update the text widget
        self.status_bar.config(state=tk.NORMAL)
        self.status_bar.delete("1.0", tk.END)
        for text, tag in status_parts:
             self.status_bar.insert(tk.END, text, tag)
        self.status_bar.config(state=tk.DISABLED)


    def _clear_text_widget(self, widget):
        widget.config(state=tk.NORMAL)
        widget.delete("1.0", tk.END)
        widget.config(state=tk.DISABLED)
        
    def _load_chat_history(self, history: List[str]):
        """Populates the chat window with historical messages."""
        self._clear_text_widget(self.chat_text)
        self.chat_text.config(state=tk.NORMAL)

        agent_name = f"{self.agent_name_var.get()}:"
        user_name = f"{self.user_name_var.get()}:"

        for message in history:
            if message.startswith(agent_name):
                prefix = f"{agent_name} "
                msg_content = message[len(agent_name):].lstrip()
                tag = "agent_chat"
            elif message.startswith(user_name):
                prefix = f"{user_name} "
                msg_content = message[len(user_name):].lstrip()
                tag = "user_chat"
            else: # Fallback for system messages or malformed history
                prefix = ""
                msg_content = message
                tag = "info"
            
            self.chat_text.insert(tk.END, f"{prefix}{msg_content}\n\n", tag)
            
        self.chat_text.config(state=tk.DISABLED)
        self.chat_text.see(tk.END)


    def process_incoming(self):
        """ Overhauled to handle new menu system and popups. """
        while not self.output_q.empty():
            try:
                message = self.output_q.get_nowait()
                msg_type = message.get("type")
                payload = message.get("payload")

                if msg_type == "update_memory_log":
                    self.update_memory_log(payload.get("memory_content", {}))
                elif msg_type == "load_chat_history":
                    self._load_chat_history(payload)
                elif msg_type == "update_persistent_stats":
                    self.persistent_token_vars["prompt"].set(f"{payload.get('prompt_tokens', 0):,}")
                    self.persistent_token_vars["completion"].set(f"{payload.get('completion_tokens', 0):,}")
                    self.persistent_token_vars["total"].set(f"{payload.get('total_tokens', 0):,}")
                    self.persistent_token_vars["api_requests"].set(f"{payload.get('api_requests', 0):,}")
                elif msg_type == "update_full_context":
                    self.update_full_context(payload.get("full_context", ""), tag=payload.get("tag", None))
                elif msg_type == "log_input":
                    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                    tag = payload.get("tag", "input_log")
                    header = f"--- INPUT SENT TO API @ {timestamp} ---"
                    full_log_content = f"{header}\n{payload['log_content']}"
                    self.add_log_message(full_log_content, tag)
                elif msg_type == "new_message":
                    tag = payload.get("tag", "output_log")
                    if payload.get("raw_log"):
                        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        header = f"--- OUTPUT RECEIVED FROM API @ {timestamp} ---"
                        raw_log = payload['raw_log']
                        usage_data = payload.get("usage")

                        token_info_str = ""
                        if usage_data:
                            prompt_tokens = usage_data.get('prompt_tokens', 0)
                            completion_tokens = usage_data.get('completion_tokens', 0)
                            total_tokens = usage_data.get('total_tokens', 0)
                            token_info_str = (f"\n\n--- TOKENS (This Turn) ---\nPrompt: {prompt_tokens} | Completion: {completion_tokens} | Total: {total_tokens}")

                        full_log_content = f"{header}\n{raw_log}{token_info_str}"
                        self.add_log_message(full_log_content, tag)

                    if payload.get("sanitized_message"):
                        chat_tag = payload.get("chat_tag", "agent_chat")
                        self.add_chat_message(f"{self.agent_name_var.get()}: ", payload["sanitized_message"], chat_tag)

                elif msg_type == "system_prompt_loaded":
                    self.sys_prompt_text.delete("1.0", tk.END)
                    self.sys_prompt_text.insert("1.0", payload)
                elif msg_type == "input_injector_loaded":
                    self.injector_text.delete("1.0", tk.END)
                    self.injector_text.insert("1.0", payload)
                elif msg_type == "all_prompts_data":
                    self._populate_system_prompts_editor(payload)
                elif msg_type == "summarizer_prompts_data":
                    self._populate_summarizer_prompts_editor(payload)
                elif msg_type == "status_update":
                    self.status_data.update(payload)
                    if "memory" in payload: self.update_memory_log(payload["memory"])
                elif msg_type == "api_key_validation_status":
                    self.status_data["api_status"] = "Valid" if payload else "Invalid"
                    if not payload: messagebox.showerror("API Key Error", "The provided Google API key is invalid or lacks the required permissions. Please set a valid key via the API menu.")
                elif msg_type == "tts_voices_list":
                    self._populate_voices_menu(payload)
                elif msg_type == "tts_playback_started":
                    self.status_data["info"] = "Speaking..."
                elif msg_type == "tts_playback_finished":
                    self.status_data["info"] = "Ready"
                elif msg_type == "user_input_processed":
                    self.user_input_pending = False
                    self.input_entry.config(state=tk.NORMAL)
                    self.send_button.config(state=tk.NORMAL)
                    self.input_entry.focus_set()
                    self.status_data["info"] = "Ready"
                elif msg_type == "set_user_status":
                    self.user_status_var.set(payload)
                elif msg_type == "ping_user":
                    agent_name = self.agent_name_var.get()
                    self.bell()
                    self.deiconify()
                    self.lift()
                    self.focus_force()
                    messagebox.showinfo(f"Ping from {agent_name}", f"{agent_name} has sent you a ping!")
                elif msg_type == "error":
                    messagebox.showerror("Backend Error", payload)
                elif msg_type == "log_generation_failure":
                    self.add_log_message(payload['log_content'], "error_log")
                elif msg_type == "clear_all_ui_logs":
                    self._clear_text_widget(self.chat_text)
                    self._clear_text_widget(self.stm_log_text)
                    self._clear_text_widget(self.full_context_text)
                    self._clear_text_widget(self.log_text)
                    self.add_chat_message("System: ", "Hard reset complete. All logs and memory have been cleared.", "info")
                    self.update_memory_log({})
                    self.update_full_context("")
                elif msg_type == "set_auto_turn_state":
                    self.auto_turn_var.set(payload)
                    self._update_auto_turn_label()

            except queue.Empty:
                break
            except Exception as e:
                print(f"Error processing GUI message: {e}")

        self._update_status_bar()
        self.after(100, self.process_incoming)

    def _send_to_manager(self, cmd_type: str, payload: Any):
        try:
            self.input_q.put({"type": cmd_type, "payload": payload})
        except Exception as e:
            messagebox.showerror("Queue Error", f"Could not send command to backend: {e}")