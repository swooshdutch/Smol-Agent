[<-- README.md](README.md) | [Next: TECHNICAL_DOC.md -->](TECHNICAL_DOC.md)
---
# Project Smol Agent - User Manual

## 1. Introduction

Welcome to Project Smol Agent! This application provides a framework for running a persistent, interactive AI agent on your own machine. Unlike a simple chatbot, this agent has a memory system, the ability to interact with files, and a highly customizable "personality" and instruction set defined by you.

The core concept is that the agent operates in "turns." In each turn, it gathers information about its environment (time, user status, chat history, its own memories), reflects on its current goals (its "self-prompt"), and then decides what to do next. This could be talking to you, reading a file, writing some code, or simply thinking and planning its next move.

This manual will guide you through every feature of the user interface (GUI), explain how to configure your agent, and teach you how to effectively command it through prompting.

---

## 2. The Main Window: A Guided Tour

The main window is divided into three primary vertical sections, plus a top menu bar and a bottom input/status bar.

### The Left Pane: The Control Panel

This panel contains all the primary, real-time controls for the agent's behavior and settings.

- **Save Settings Button**: This is your most important button! It saves **everything**: window sizes, pane layouts, all prompt changes made via the menu, generation parameters, and all other settings. It does **not** save the agent's current memory or chat log; that is saved automatically as part of its state.

- **Hard Reset Agent Button**: This is a powerful "factory reset" for the agent's *state*, not your settings.
    - **What it DOES**: Wipes the agent's short, medium, and long-term memory. Clears the chat history. Wipes the contents of all files in the `/terminal/` directory. Resets the agent to its initial `self-prompt`.
    - **What it DOES NOT**: Reset your API key, your saved prompt files, or any of the settings in this control panel.
    - Use this when you've made significant changes to the agent's main prompt and want to see how it behaves from a completely fresh start.

- **Agent Auto-Turn**:
    - **Enabled/Disabled Switch**: When enabled, the agent will automatically take a turn after the specified duration of inactivity. This is how the agent can "work" on tasks autonomously. When disabled, the agent will only take a turn when you send it a message.
    - **Duration (s)**: Sets the inactivity timer (in seconds) for the auto-turn.

- **Generation Parameters**: These settings control the "creativity" and "randomness" of the Google Gemini model's responses.
    - **Advice**: The default settings are a good, balanced starting point. If you find the agent is too repetitive, try increasing the `Temperature`. If it's too chaotic or nonsensical, try lowering it.
    - **Temperature**: Controls the randomness of the output. Higher values (e.g., 1.0) make the output more random and creative. Lower values (e.g., 0.3) make it more focused and deterministic.
    - **Top-K**: Limits the model's choices for the next word to the `K` most likely options. A lower value can make the text more coherent but less surprising.
    - **Top-P**: An alternative to Temperature, this method selects from the smallest possible set of words whose cumulative probability exceeds the value `P`.
    - **Reset Button**: Restores these parameters to their default values.

- **Persistent Usage Stats**: This section tracks your Google Gemini API usage across all sessions.
    - **Input/Output/Total Tokens**: Shows the number of tokens sent to and received from the API. This is useful for monitoring costs.
    - **API Requests**: Shows the total number of times the application has called the API.
    - **Reset Buttons**: These will reset the corresponding counters to zero. This is a permanent action and only affects the numbers displayed here.

- **Controls**:
    - **User Status**: This dropdown informs the agent of your current status. The agent receives this in its prompt, and it can influence its behavior. For example, auto-turn will pause if your status is `offline`.
    - **Voice (TTS) Switch**: Enables or disables Text-to-Speech (TTS). When enabled, the agent's replies in the chat will be spoken aloud using the voice selected in the "Voices" menu.

### The Center Pane: Sanitized Chat

This is your main interaction window. It displays a clean, readable version of your conversation with the agent.
- **User messages** appear in one color.
- **Agent messages** appear in another.
- **System messages** (like "Settings saved.") appear in a gray, italic font.

### The Right Pane: The Agent's Inner World

This area is for advanced users and prompters who want to see what's happening "under the hood."

- **Tiered Memory Viewer**: Displays the agent's memory, which is divided into three tiers:
    - **LTM (Long-Term Memory)**: Core, foundational memories that are distilled over time.
    - **MTM (Medium-Term Memory)**: Synthesized memories from recent events, forming more abstract concepts.
    - **STM (Short-Term Memory)**: A summary of the agent's most recent turn (what it thought, said, and did).
    - Memory flows upwards: After each turn, a new STM entry is created. When STM is full, a batch of entries is consolidated into a new MTM entry. The same process occurs from MTM to LTM.

- **Full Context**: This is arguably the most important window for debugging your prompts. It shows the **exact, complete text** that is sent to the Gemini API for the current turn. If your agent is behaving strangely, inspect this window to see what information and instructions it was actually working with.

- **Raw LLM Log**: This shows the raw, un-sanitized response received from the API. It includes the agent's `{thinking: ...}` blocks, all commands it tried to execute, and token usage statistics for that specific turn. File commands are highlighted in green for easy identification.

### The Bottom Bar: Input & Status

- **Input Entry & Send Button**: Where you type your messages to the agent. Pressing `Enter` is the same as clicking `Send`.
- **Status Bar**: A quick overview of the application's state.
    - **API**: Shows the status of your Google API Key (e.g., `Valid`, `Invalid`, `Initializing`).
    - **LLM**: Shows the agent's current state (e.g., `Idle`, `Generating...`).
    - **User**: Your currently selected user status.
    - **Auto-Turn**: Shows `ON` or `OFF`.
    - **Timer**: A countdown to the next auto-turn, or a status message like "Paused (typing...)".
    - **Info**: General status messages like `Ready` or `Speaking...`.

---

## 3. The Top Menu Bar: Settings & Customization

This menu is your gateway to configuring the agent's core identity and behavior.

### API Menu

- **Set Google API Key...**: Opens a window to enter your Google Gemini API key. You can get a key from the [Google AI Studio](https://aistudio.google.com/app/apikey). The application will not function without a valid key.

### Prompts Menu

This is where you shape the mind of your agent.
**A Note on Variables**: In these prompts, you can use `{NAME}` and `{USER}`. The application will automatically replace these with the Agent and User names you've set in the `Main Prompt` editor window.

- **Main Prompt...**: This is the most important prompt. It defines the agent's core identity, its purpose, its rules, and its personality.
    - **Advice**: Be clear and direct. Tell the agent what it is, what its goals are, and how it should behave. This is the place to instruct it on how and when to use its file-based commands.
    - The editor window also contains fields to set the `{NAME}` and `{USER}` variables.

- **Summarizer Prompts...**: This advanced menu lets you edit the prompts used for memory consolidation.
    - **Advice**: The default prompts are well-tuned for their purpose. You should only edit these if you have a specific reason and understand how they work. Each prompt's job is to take a block of text (`__TEXT_TO_SUMMARIZE__`) and condense it into a single, concise memory entry.
    - **STM Prompt**: Summarizes the agent's entire raw output from a single turn.
    - **MTM Prompt**: Takes a list of short-term memories and synthesizes them into a more abstract medium-term memory.
    - **LTM Prompt**: Takes a list of medium-term memories and distills them into a foundational, high-level core memory.

- **System Prompts...**: This menu contains a collection of other prompt templates that define how the agent interacts with its systems.
    - **input_injector**: This text is added to the `Full Context` on every single turn. It's useful for global, unchanging rules you always want the agent to follow.
    - **prompt_templates**: This is a list of all the feedback messages the agent receives from the "Terminal" when it performs actions.
        - **Advice**: You can edit these to change the agent's "internal voice." For example, you could make file error messages more robotic, or success messages more enthusiastic. You are defining the feedback loop for the agent's tool use.
        - The placeholders like `__FILENAME__`, `__CONTENT__`, `__LIMIT__`, `__ALLOWED_EXTENSIONS__` are filled in automatically by the system.

### Options Menu

- **Logs...**: Lets you change the font size for the Chat and Log panes.
- **Memory Manager...**: Control the agent's context and memory limits.
    - **Memory Capacities**: Set the maximum number of entries for STM, MTM, and LTM before consolidation is triggered.
    - **Chat Log Messages in Context**: How many of the most recent chat messages are included in the `Full Context`.
    - **Max File Character Count**: The maximum size (in characters) for a `.txt` file in the `/terminal/`. The agent will receive an error if it tries to exceed this.
    - **Max Terminal Files**: The maximum number of files the agent can create in the `/terminal/` directory.
- **Window Order...**: Allows you to re-arrange the three panes on the right side of the window (Memory, Full Context, Raw Log) to your preference.

### Voices Menu

This menu will be populated with all the Text-to-Speech voices installed on your operating system. Simply select the one you'd like the agent to use. You must click `Save Settings` in the left pane for this choice to be saved for future sessions.

---

## 4. Prompting Guide: Commanding Your Agent

The agent's behavior is driven entirely by its prompts. It reads your instructions and then generates a response that includes its thoughts, speech, and commands.

### The Agent Command Syntax

To use its tools, the agent must generate commands in a specific `{...}` format in its `Raw LLM Log` output. You, as the prompter, must instruct the agent (primarily in the `Main Prompt`) on how and when to use these commands.

- **`{thinking: ...}` - (MANDATORY)**
  The agent's internal monologue. This block is **required** in every response. It's where the agent processes information and decides on its actions. If this block is missing, the response is considered invalid and will be retried.

- **`{{self-prompt-from-{NAME}}: ...}` - (MANDATORY)**
  The agent's goal or directive for its **next** turn. This is the engine of its autonomy. It's how the agent chains thoughts and actions together across multiple turns. This is also **required** in every response.

- **`{{NAME}-says: ...}`**
  Whatever is in this block will be displayed as a message from the agent in the `Sanitized Chat` window.

- **`{create-file-filename.ext}`**
  Creates a new, empty file in the `/terminal/` directory.

- **`{read-file-filename.ext}`**
  Reads the content of the specified file. The content will be injected into the `Full Context` on the agent's *next* turn.

- **`{delete-file-filename.ext}`**
  Deletes the specified file from the `/terminal/` directory.

- **`{push-update-filename.txt: content to add...}`**
  For `.txt` files, this appends the content as a new, numbered `{entry-X: ...}`.

- **`{push-update-filename.py: full new content...}`**
  **IMPORTANT**: For any file that is **not** a `.txt` file (e.g., `.py`, `.json`, `.html`), this command **OVERWRITES** the entire file with the new content. This is designed for writing and editing code or structured data.

- **`{filename.txt-entry-3-delete}`**
  Deletes a specific numbered entry from a `.txt` file.

- **`{ping-user}`**
  Sends a system notification to your desktop to get your attention.

### How to Instruct Your Agent

Your primary tool for instruction is the **Main Prompt**. You need to tell the agent *that these tools exist* and *how it should use them*.

**Example 1: A Coder Agent**
In your Main Prompt, you might write:
> You are a Python programming assistant. Your goal is to help me write and debug code. To begin, ask me what script I want to create. Use the `{create-file-script_name.py}` command to create the file. Then, use `{push-update-script_name.py: ...}` to write the code into it. You can read the file to check your work with `{read-file-script_name.py}`.

**Example 2: A Research Agent**
In your Main Prompt, you could instruct:
> You are a research analyst. I will provide you with data by telling you to read files. For example, if I say "read the project notes", you should use the command `{read-file-project_notes.txt}`. After analyzing the contents, you must create a summary file using `{create-file-summary.txt}` and write your key findings to it using `{push-update-summary.txt: ...}`.

**The key takeaway is that the agent is not aware of these commands by default. Your prompt is what teaches it to use its own abilities.**

---

## 5. Troubleshooting & Best Practices

- **Agent isn't responding or seems "stuck"**:
  1. Check the Status Bar. Does it say `API: Invalid`? If so, your API key is wrong.
  2. Look at the `Raw LLM Log`. Are there any error messages? The model might be failing to generate a valid response (e.g., forgetting the `{thinking}` block).
  3. The model might be generating a response that is being blocked by Google's safety filters. The `Raw LLM Log` may show a block reason.

- **Agent is behaving unexpectedly**:
  - The `Full Context` window is your best friend. Read it carefully. What you *think* you told the agent and what it *actually* received in its context can be different. Your issue is almost always a misunderstanding that can be corrected by adjusting your prompts.

- **Agent is repeating itself**:
  - It might be stuck in a self-prompt loop. Check the `self-prompt` it's generating in the `Raw LLM Log`.
  - Try increasing the `Temperature` or adjusting `Top-P`/`Top-K` to encourage more varied responses.
  - A `Hard Reset` can break it out of a deep loop.

- **Best Practices**:
  - **Save Often**: Click `Save Settings` after making changes you want to keep.
  - **Iterate Small**: When editing prompts, make small, incremental changes and observe the results. Don't try to change everything at once.
  - **Reset for Big Changes**: When you make a major change to the `Main Prompt`, use the `Hard Reset Agent` button to see its effect on a clean slate.
  - **Experiment!**: The best way to learn is to try things out. Change the prompt templates, give the agent a new personality, and see what happens. There's no right or wrong way to prompt!