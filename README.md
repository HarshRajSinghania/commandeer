# Commandeer

Commandeer is an AI-powered command execution system that provides a VS Code-inspired terminal interface for executing natural language commands. It combines persistent PTY sessions with AI planning to safely execute complex tasks.

## Features

- **AI-Powered Command Planning**: Convert natural language requests into safe shell commands
- **Persistent PTY Sessions**: Maintain stateful terminal sessions across commands
- **VS Code-Inspired TUI**: Modern terminal interface with project tree, command history, and AI todo list
- **REST API & WebSocket Interface**: Programmatic access to command execution
- **Safety Checking**: Automatic detection of potentially dangerous commands
- **Interactive Planning**: Step-by-step execution with user confirmation for risky operations

## Architecture

```
┌─────────────────┐    ┌──────────────────┐    ┌──────────────────┐
│   TUI Frontend  │◄──►│  AI Command Flow │◄──►│ PTY Session Mgr  │
└─────────────────┘    └──────────────────┘    └──────────────────┘
                              │                         │
                              ▼                         ▼
                    ┌──────────────────┐    ┌──────────────────┐
                    │   OpenAI API     │    │   Shell Process  │
                    └──────────────────┘    └──────────────────┘
```

## Components

### 1. PTY Session Manager (`src/pty_manager.py`)
- Manages persistent terminal sessions using Unix PTY
- Handles command execution, output streaming, and session lifecycle
- Provides thread-safe session management

### 2. AI Command Planner (`src/ai_planner.py`)
- Converts natural language to shell commands using OpenAI API
- Implements safety checking for dangerous commands
- Generates step-by-step execution plans with risk assessment

### 3. REST API Server (`src/api_server.py`)
- Provides HTTP interface for session management and command execution
- Supports session creation, command execution, and control characters
- CORS-enabled for web integration

### 4. WebSocket Server (`src/websocket_server.py`)
- Real-time communication for live command output streaming
- Bidirectional communication for interactive terminal sessions
- Connection management and output broadcasting

### 5. Terminal UI (`src/tui_app.py`)
- VS Code-inspired textual interface
- Project tree, command history, and AI todo list
- Keyboard navigation and dark theme styling

### 6. Command Flow (`src/command_flow.py`)
- Orchestrates AI planning with command execution
- Manages command queues and streaming output
- Integrates with TUI for real-time updates

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-username/commandeer.git
cd commandeer
```

2. Install dependencies:
```bash
pip install -r requirements.txt
```

3. Set up environment variables:
```bash
cp .env.example .env
# Edit .env with your OpenAI API key and other settings
```

## Usage

### Starting the Backend Services

```bash
python src/main.py
```

This starts both the REST API (port 8765) and WebSocket server (port 8766).

### Command Line AI Planning

```bash
# Direct execution
python src/ai_main.py --goal "create a new directory called 'my-project' and initialize git"

# Interactive mode with user confirmation
python src/ai_main.py --goal "delete all .tmp files in /tmp" --interactive
```

### Terminal UI

```bash
# VS Code-inspired TUI
python src/tui_main.py

# With light theme
python src/tui_main.py --theme light
```

### Automation Mode

```bash
# Command line automation
python src/automation_main.py --goal "set up a new Python project with virtual environment"

# TUI automation
python src/automation_main.py --goal "deploy my web application" --tui
```

## API Endpoints

### REST API (http://localhost:8765)

- `POST /sessions` - Create new PTY session
- `GET /sessions` - List active sessions
- `GET /sessions/{id}` - Get session status
- `POST /execute` - Execute command in session
- `POST /control` - Send control character (Ctrl+C, etc.)
- `POST /resize` - Resize terminal dimensions
- `DELETE /sessions/{id}` - Close session

### WebSocket (ws://localhost:8766)

- `connect` - Connect to PTY session
- `command` - Execute command
- `control` - Send control character
- `resize` - Resize terminal

## Safety Features

- **Dangerous Command Detection**: Automatically identifies risky commands like `rm -rf /`
- **User Confirmation**: Requires approval for dangerous operations
- **Risk Assessment**: Categorizes commands as safe, caution, dangerous, or critical
- **Alternative Suggestions**: Provides safer alternatives when available

## Testing

```bash
# Test TUI functionality
python test_tui.py

# Test backend services
python test_backend.py

# Test AI planning
python test_ai_planner.py

# Complete application test
python test_complete_app.py
```

## Configuration

The application can be configured through environment variables in `.env`:

- `OPENAI_API_KEY` - Your OpenAI API key
- `OPENAI_BASE_URL` - API endpoint (default: https://api.openai.com/v1)
- `AI_MODEL` - Model to use (default: gpt-3.5-turbo)

## Requirements

- Python 3.8+
- OpenAI API key
- Unix-like system (Linux/macOS) for PTY support

## License

MIT License - see LICENSE file for details.

## Contributing

1. Fork the repository
2. Create a feature branch
3. Commit your changes
4. Push to the branch
5. Create a Pull Request