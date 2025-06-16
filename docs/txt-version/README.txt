# Project Smol Agent

Welcome to Project Smol Agent, a desktop application for running a persistent, stateful AI companion powered by Google's Gemini API. This project moves beyond simple chatbots, providing an agent with a tiered memory system, file I/O capabilities, and a highly customizable personality, all running locally on your machine.

The agent operates in a continuous loop, perceiving its environment, thinking based on its instructions, and acting on its conclusions. This allows it to remember past conversations, work on multi-step tasks, and evolve over time based on your interactions.



---

## Features

*   **Persistent State:** The agent's memory and conversation history are saved, allowing it to maintain context across sessions.
*   **Tiered Memory System:** A simplified cognitive model with Short-Term, Medium-Term, and Long-Term memory that the agent manages itself.
*   **File-Based Tool Use:** The agent can be instructed to read, write, edit, and delete files in a sandboxed `terminal` directory, allowing it to maintain notes, write code, or manage data.
*   **Fully Customizable Personality:** You define the agent's core identity, goals, and rules through a powerful and user-friendly prompting system.
*   **Autonomous Operation:** An "Auto-Turn" feature allows the agent to work on tasks independently without requiring constant user input.
*   **Decoupled & Responsive UI:** The backend logic runs in a separate thread from the UI, ensuring the application remains responsive even while the agent is thinking.
*   **Text-to-Speech (TTS):** The agent can speak its responses aloud using your operating system's built-in voices.
*   **Token & Cost Tracking:** The UI displays persistent API usage statistics to help you monitor your costs.

---

## Getting Started

Follow these steps to get the project up and running on your local machine.

### 1. Prerequisites

*   Python 3.8 or newer.
*   A Google Gemini API Key. You can get a free key from the [Google AI Studio](https://aistudio.google.com/app/apikey).

### 2. Installation & Dependencies

First, clone this repository to your local machine or download and extract the source code ZIP file.

Next, you need to install the required Python libraries. You can install them one by one using the `pip` commands below. Open a terminal or command prompt and run each of these commands:

pip install google-generativeai

pip install pyttsx3

pip install pythoncom

*Note: `pythoncom` is part of the `pywin32` package. If the command above fails, especially on non-Windows systems, you might need `pip install pywin32` for Windows or you can ignore this dependency if you are on macOS or Linux, as it is only used for TTS COM initialization on Windows.*

### 3. Running the Application

Once the dependencies are installed, navigate to the project's root directory in your terminal and run the `main.py` script:

`python main.py`

The first time you launch the application, it will automatically create the necessary directories (`/terminal`, `/memory`, `/prompts`) and default prompt files.

### 4. Initial Configuration

1.  When the application window appears, the first thing you need to do is set your API key.
2.  Go to the top menu and click **API > Set Google Gemini API Key...**.
3.  Paste your key into the text field and click "Save & Apply".
4.  The status bar at the bottom should update to show `API: Valid`. If it shows `API: Invalid`, double-check that your key is correct and has the necessary permissions.

You are now ready to start interacting with your agent!

---

## How to Use

The application is designed to be intuitive, but here are the key concepts:

*   **The Main Prompt:** This is the most important setting. Go to **Prompts > Main Prompt...** to define your agent's personality, goals, and rules. This is where you will "teach" the agent how to use its file-based tools (e.g., `{create-file-notes.txt}`).
*   **The Control Panel (Left Pane):** Here you can control the agent's behavior in real-time. Enable `Auto-Turn` to let it work on its own, adjust the `Generation Parameters` to change its creativity, and click `Save Settings` to make your changes permanent.
*   **The "Inner World" (Right Pane):** For advanced users, these panes are invaluable.
    *   **Tiered Memory Viewer:** See what the agent remembers.
    *   **Full Context:** See the *exact* prompt being sent to the LLM on each turn. This is your primary tool for debugging your instructions.
    *   **Raw LLM Log:** See the agent's unfiltered "thoughts" and the commands it executes.
*   **Hard Reset:** If you make a major change to the Main Prompt and want to see how the agent behaves from a fresh start, use the **Hard Reset Agent** button. This wipes its memory and chat history but does *not* affect your saved settings or prompts.

## Documentation

For a complete guide to all features, settings, and prompting techniques, please refer to the documents included with the project:

*   **User Manual:** A comprehensive guide for all users, explaining every UI element and providing advice on effective prompting.
*   **Technical & Developer Documentation:** An in-depth guide for developers looking to understand the codebase, extend the agent's functionality, or integrate it with other systems.

---

We hope you enjoy experimenting with your own personal AI. Happy prompting!