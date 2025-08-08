#!/usr/bin/env python3
"""
VS Code-inspired TUI Application
Provides a modern terminal interface with AI command planning
"""

import asyncio
import json
from typing import List, Dict, Any, Optional
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header, Footer, Input, Button, Static, ListView, ListItem, 
    TextArea, Label, DataTable, Markdown
)
from textual.binding import Binding
from textual.screen import Screen
from textual.reactive import reactive
from rich.text import Text
from rich.panel import Panel
from rich.console import Console
import websockets
import threading
import time
import os

from src.ai_planner import AICommandPlanner, AISafetyChecker
from src.planning_loop import InteractivePlanner
from src.pty_manager import manager


class CommandHistory:
    """Manages command history and outputs"""
    
    def __init__(self):
        self.commands: List[Dict[str, Any]] = []
        self.current_index = 0
    
    def add_command(self, command: str, output: str, success: bool):
        """Add a command to history"""
        self.commands.append({
            "command": command,
            "output": output,
            "success": success,
            "timestamp": time.time()
        })
    
    def get_recent(self, count: int = 10) -> List[Dict[str, Any]]:
        """Get recent commands"""
        return self.commands[-count:]
    
    def search(self, query: str) -> List[Dict[str, Any]]:
        """Search command history"""
        return [cmd for cmd in self.commands if query.lower() in cmd["command"].lower()]


class AITodoList:
    """Manages AI-generated todo list"""
    
    def __init__(self):
        self.items: List[Dict[str, Any]] = []
    
    def set_plan(self, plan: Dict[str, Any]):
        """Set the AI-generated plan"""
        self.items = []
        for i, step in enumerate(plan.get("steps", [])):
            self.items.append({
                "id": i + 1,
                "command": step["command"],
                "reasoning": step["reasoning"],
                "risk_level": step["risk_level"],
                "completed": False,
                "output": ""
            })
    
    def mark_completed(self, item_id: int, output: str):
        """Mark an item as completed"""
        for item in self.items:
            if item["id"] == item_id:
                item["completed"] = True
                item["output"] = output
                break
    
    def get_items(self) -> List[Dict[str, Any]]:
        """Get all todo items"""
        return self.items


class ProjectTree:
    """Manages project file tree"""
    
    def __init__(self, root_path: str = "."):
        self.root_path = root_path
        self.files = []
        self.refresh()
    
    def refresh(self):
        """Refresh the file tree"""
        self.files = []
        try:
            for root, dirs, files in os.walk(self.root_path):
                level = root.replace(self.root_path, '').count(os.sep)
                indent = ' ' * 2 * level
                self.files.append(f"{indent}{os.path.basename(root)}/")
                subindent = ' ' * 2 * (level + 1)
                for file in files:
                    self.files.append(f"{subindent}{file}")
        except PermissionError:
            self.files = ["Permission denied"]
        except Exception as e:
            self.files = [f"Error: {str(e)}"]
        except Exception as e:
            self.files = [f"Error: {str(e)}"]


class CommandPalette(Screen):
    """Command palette for quick command search"""
    
    def __init__(self, history: CommandHistory):
        super().__init__()
        self.history = history
    
    def compose(self) -> ComposeResult:
        yield Container(
            Input(placeholder="Type to search commands..."),
            ListView(),
            id="command-palette"
        )
    
    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle input changes for search"""
        results = self.history.search(event.value)
        # Update list view with results


class VSCodeTUI(App):
    """Main VS Code-inspired TUI application"""
    
    CSS = """
    /* Dark theme colors */
    $background: #1e1e1e;
    $sidebar: #252526;
    $panel: #2d2d30;
    $border: #3e3e42;
    $text: #cccccc;
    $text-muted: #969696;
    $accent: #0078d4;
    $success: #4ec9b0;
    $warning: #ffcc02;
    $error: #f14c4c;
    
    /* Main layout */
    Screen {
        background: $background;
        color: $text;
    }
    
    /* Sidebar styling */
    .sidebar {
        background: $sidebar;
        border-right: solid $border;
        padding: 1;
    }
    
    .panel {
        background: $panel;
        border: solid $border;
        padding: 1;
    }
    
    /* Header styling */
    Header {
        background: $sidebar;
        color: $text;
        border-bottom: solid $border;
    }
    
    /* Input styling */
    Input {
        background: $panel;
        color: $text;
        border: solid $border;
    }
    
    /* Button styling */
    Button {
        background: $accent;
        color: white;
        border: none;
    }
    
    /* List styling */
    ListView {
        background: $sidebar;
        border: solid $border;
    }
    
    ListItem {
        background: $sidebar;
        color: $text;
    }
    
    ListItem:hover {
        background: $accent;
    }
    
    /* Text area styling */
    TextArea {
        background: $background;
        color: $text;
        border: solid $border;
    }
    
    /* Status indicators */
    .success { color: $success; }
    .warning { color: $warning; }
    .error { color: $error; }
    .muted { color: $text-muted; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+p", "show_command_palette", "Command Palette"),
        Binding("tab", "focus_next", "Next Pane"),
        Binding("shift+tab", "focus_previous", "Previous Pane"),
        Binding("enter", "execute_command", "Execute"),
        Binding("ctrl+c", "cancel_command", "Cancel"),
    ]

    def __init__(self):
        super().__init__()
        self.history = CommandHistory()
        self.todo_list = AITodoList()
        self.project_tree = ProjectTree()
        self.ai_planner = None
        self.current_session = "tui-session"
        self.output_buffer = ""
        
    def compose(self) -> ComposeResult:
        yield Header()
        
        yield Horizontal(
            # Left Sidebar - Project/Command History
            Container(
                Label("📁 Project", classes="panel-title"),
                ListView(
                    *[ListItem(Label(file)) for file in self.project_tree.files[:20]]
                ),
                Label("📝 Command History", classes="panel-title"),
                ListView(
                    *[ListItem(Label(cmd["command"])) for cmd in self.history.get_recent(5)]
                ),
                classes="sidebar",
                id="left-sidebar"
            ),
            
            # Main Content Area
            Vertical(
                # Top Panel - Command Execution
                Container(
                    Label("⚡ Command Output", classes="panel-title"),
                    TextArea(
                        placeholder="Command output will appear here...",
                        id="output-area"
                    ),
                    classes="panel",
                    id="output-panel"
                ),
                
                # Bottom Panel - Input and AI Reasoning
                Container(
                    Label("💬 User Input", classes="panel-title"),
                    Input(
                        placeholder="Enter command or natural language goal...",
                        id="command-input"
                    ),
                    Label("🤖 AI Reasoning", classes="panel-title"),
                    TextArea(
                        placeholder="AI reasoning will appear here...",
                        id="reasoning-area"
                    ),
                    classes="panel",
                    id="input-panel"
                )
            ),
            
            # Right Sidebar - AI To-Do List
            Container(
                Label("🎯 AI To-Do List", classes="panel-title"),
                ListView(
                    *[ListItem(Label(f"{item['id']}. {item['command']}")) 
                      for item in self.todo_list.get_items()]
                ),
                classes="sidebar",
                id="right-sidebar"
            )
        )
        
        yield Footer()

    def on_mount(self):
        """Initialize the application"""
        # Create PTY session
        if not manager.get_session(self.current_session):
            manager.create_session(self.current_session)
        
        # Setup AI planner
        api_key = os.getenv("OPENAI_API_KEY", "mock-key")
        self.ai_planner = AICommandPlanner(api_key)
        self.ai_planner.set_pty_manager(manager)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle command input submission"""
        if event.input.id == "command-input":
            self.execute_natural_language(event.value)

    def execute_natural_language(self, text: str) -> None:
        """Execute natural language command"""
        try:
            # Use AI planner to generate plan
            try:
                plan = self.ai_planner.planner.generate_plan(text)
            except Exception as e:
                self.query_one("#output-area").text = f"Error generating plan: {str(e)}"
                return
            self.todo_list.set_plan(plan)
            
            # Display reasoning
            reasoning_text = "\n".join([f"{step['command']}: {step['reasoning']}" 
                                      for step in plan.get("steps", [])])
            self.query_one("#reasoning-area").text = reasoning_text
            
            # Execute plan
            interactive = InteractivePlanner(self.ai_planner)
            result = interactive.interactive_execute(text, self.current_session)
            
            # Update output
            output_text = json.dumps(result, indent=2)
            self.query_one("#output-area").text = output_text
            
            # Update history
            self.history.add_command(text, output_text, result.get("status") == "success")
            
        except Exception as e:
            self.query_one("#output-area").text = f"Error: {str(e)}"

    def action_show_command_palette(self) -> None:
        """Show command palette"""
        self.push_screen(CommandPalette(self.history))

    def action_execute_command(self) -> None:
        """Execute current command"""
        input_widget = self.query_one("#command-input")
        if input_widget.value:
            self.execute_natural_language(input_widget.value)

    def action_cancel_command(self) -> None:
        """Cancel current command"""
        self.query_one("#command-input").value = ""
        self.query_one("#reasoning-area").text = "Command cancelled"

    def on_unmount(self):
        """Cleanup on exit"""
        manager.close_session(self.current_session)


if __name__ == "__main__":
    app = VSCodeTUI()
    app.run()