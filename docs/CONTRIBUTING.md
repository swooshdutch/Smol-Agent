[<-- README.md](README.md) | [<-- TECHNICAL_DOC.md](TECHNICAL_DOC.md)
---
# Contributing to Project Smol Agent

Thank you for your interest in contributing! We welcome bug fixes, feature enhancements, and other improvements. This project is designed to be an extensible framework, and we're excited to see what the community builds with it.

Before you begin, please review this guide to understand the project's architecture and contribution workflow.

## Core Architectural Principles

To contribute effectively, it's essential to understand the project's decoupled design:

1.  **Two-Thread Model:** The application runs on two main threads.
    *   **GUI Thread (`gui.py`):** Handles all Tkinter UI rendering and user input. It is non-blocking and should *never* perform long-running tasks like API calls or file I/O.
    *   **Backend Thread (`chat_manager.py`):** Manages all agent logic, state, API calls, and file operations. It is completely headless.

2.  **Queue-Based Communication:** The threads communicate exclusively through two thread-safe `queue.Queue` instances. The GUI puts command messages on an input queue, and the `ChatManager` puts UI update messages on an output queue. This prevents race conditions and keeps the code clean.

**When making changes, always respect this separation.** A new feature should almost always involve logic in the `ChatManager` and, if necessary, a new message type to inform the `GUI` of updates.

## How to Add a New Agent Command

This is the most common way to extend the agent's capabilities. For a detailed walkthrough, see the [Technical Documentation](TECHNICAL_DOC.md).

**High-Level Steps:**

1.  **Update Regex:** In `chat_manager.py`, add your new command's syntax to the regex patterns in the `_update_dynamic_patterns` method.
2.  **Create Handler Method:** In `chat_manager.py`, create a new `_handle_your_command()` method containing the Python logic for your feature. It should return a formatted string as feedback for the agent.
3.  **Route Command:** In `chat_manager.py`, add routing logic to `_execute_agent_command` to call your new handler when its command pattern is matched.
4.  **Add Feedback Templates:** In `main.py`, add new prompt templates to `get_default_config()` so the agent knows what feedback to expect (e.g., `{Terminal: your-command-success}`).
5.  **Teach the Agent:** Remember to update the Main Prompt in the UI to teach the agent about its new skill!

## Submitting a Pull Request

1.  Fork the repository to your own GitHub account.
2.  Create a new branch for your feature or bug fix (e.g., `feature/add-calculator` or `fix/log-pane-scrolling`).
3.  Make your changes, committing them with clear and concise messages.
4.  Ensure your code works and doesn't introduce any obvious regressions.
5.  Submit a pull request to the `main` branch of the original repository.
6.  In your pull request description, please explain the changes you've made and why.

We appreciate your contributions and will review your pull request as soon as possible.