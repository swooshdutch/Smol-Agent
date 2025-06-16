# Project Smol Agent

A desktop application for running a persistent, stateful AI companion powered by Google's Gemini API. This project provides a framework for an AI that remembers conversations, uses file-based tools, and has a fully customizable personality defined by you.

 
*(Image is representative of the UI layout)*

[USER_MANUAL.md](USER_MANUAL.md) | [TECHNICAL_DOC.md](TECHNICAL_DOC.md) | [CONTRIBUTING.md](CONTRIBUTING.md)
---

## Key Features

*   **🧠 Persistent Memory:** A tiered memory system (STM, MTM, LTM) allows the agent to learn and recall information across sessions.
*   **🛠️ Tool Use:** Teach the agent to read, write, and edit files in its sandboxed directory to manage notes, write code, or build a knowledge base.
*   **🎨 Fully Customizable:** You define the agent's core identity, goals, and rules through a powerful and user-friendly prompting system.
*   **🚀 Autonomous Operation:** An "Auto-Turn" feature allows the agent to work on tasks independently without requiring constant user input.
*   **🗣️ Text-to-Speech:** The agent can speak its responses aloud using your operating system's built-in voices.

## Quick Start

### 1. Prerequisites

*   Python 3.8+
*   A Google Gemini API Key from the [Google AI Studio](https://aistudio.google.com/app/apikey).

### 2. Installation

Clone this repository, then install the required Python libraries using `pip`:

`pip install google-generativeai`

`pip install pyttsx3`

`pip install pythoncom`
*(Note: `pythoncom` is part of `pywin32`. On non-Windows systems, this dependency may not be required.)*

### 3. Run the Application

Navigate to the project directory and run:

`python main.py`

On first launch, the app will create all necessary directories and default prompts. You will need to enter your Google Gemini API key via the **API > Set Google Gemini API Key...** menu.

## Documentation Hub

This project is extensively documented to help you get the most out of it.

*   **📖 [User Manual](USER_MANUAL.md):** The complete guide for all users. Learn about every feature, setting, and prompting technique to shape your ideal AI companion.

*   **⚙️ [Technical Documentation](TECHNICAL_DOC.md):** For developers. A deep dive into the architecture, data flow, and code, explaining how everything works under the hood.

*   **🤝 [Contributing Guide](CONTRIBUTING.md):** Interested in extending the project or fixing a bug? Start here to learn about the contribution process and core architectural principles.