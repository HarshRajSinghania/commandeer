#!/usr/bin/env python3
"""
TUI Automation Interface
Provides the complete VS Code-like experience with AI-driven automation
"""

import asyncio
import json
import os
from textual.app import App, ComposeResult
from textual.containers import Container, Horizontal, Vertical
from textual.widgets import (
    Header, Footer, Input, Button, Static, ListView, ListItem, 
    TextArea, Label, DataTable, Markdown
)
from textual.binding import Binding
from textual.reactive import reactive
from textual.message import Message
from rich.text import Text
from rich.panel import Panel
from rich.console import Console

from src.command_flow import AICommandFlow, TUICommandFlow
from src.pty_manager import manager

class AutomationTUI(App):
    """Complete TUI with AI-driven automation"""
    
    CSS = """
    /* VS Code dark theme */
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
    
    Screen {
        background: $background;
        color: $text;
    }
    
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
    
    .status-running { color: $accent; }
    .status-completed { color: $success; }
    .status-failed { color: $error; }
    """

    BINDINGS = [
        Binding("ctrl+q", "quit", "Quit"),
        Binding("ctrl+r", "run_goal", "Run Goal"),
        Binding("ctrl+c", "cancel", "Cancel"),
        Binding("tab", "focus_next", "Next"),
        Binding("shift+tab", "focus_previous", "Previous"),
    ]

    def __init__(self):
        super().__init__()
        self.ai_flow = None
        self.tui_flow = None
        self.is_running = False
        
    def compose(self) -> ComposeResult:
        yield Header()
        
        yield Horizontal(
            # Left Sidebar - Project & History
            Container(
                Label("📁 Project", classes="panel-title"),
                ListView(
                    ListItem(Label("📁 src/")),
                    ListItem(Label("  📄 pty_manager.py")),
                    ListItem(Label("  📄 api_server.py")),
                    ListItem(Label("  📄 ai_planner.py")),
                ),
                Label("📝 Command History", classes="panel-title"),
                ListView(
                    ListItem(Label("No commands yet")),
                    id="history-list"
                ),
                classes="sidebar",
                id="left-sidebar"
            ),
            
            # Main Content
            Vertical(
                # Top Panel - Live Output
                Container(
                    Label("⚡ Live Output", classes="panel-title"),
                    TextArea(
                        placeholder="Command output will appear here...",
                        id="output-area"
                    ),
                    classes="panel",
                    id="output-panel"
                ),
                
                # Bottom Panel - Input & Control
                Container(
                    Label("🎯 Goal Input", classes="panel-title"),
                    Input(
                        placeholder="Enter your goal (e.g., create a new project)...",
                        id="goal-input"
                    ),
                    Label("🤖 AI Reasoning", classes="panel-title"),
                    TextArea(
                        placeholder="AI will show reasoning here...",
                        id="reasoning-area"
                    ),
                    Button("🚀 Execute", id="execute-btn"),
                    classes="panel",
                    id="input-panel"
                )
            ),
            
            # Right Sidebar - AI To-Do List
            Container(
                Label("🎯 AI To-Do List", classes="panel-title"),
                ListView(
                    ListItem(Label("Ready to execute")),
                    id="todo-list"
                ),
                Label("📊 Status", classes="panel-title"),
                Label("Idle", id="status-label"),
                classes="sidebar",
                id="right-sidebar"
            )
        )
        
        yield Footer()

    def on_mount(self):
        """Initialize the application"""
        api_key = os.getenv("OPENAI_API_KEY", "demo-key")
        base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
        
        self.ai_flow = AICommandFlow(api_key, base_url)
        if not manager.get_session("tui-automation"):
            manager.create_session("tui-automation")
        self.ai_flow.set_session("tui-automation")
        self.tui_flow = TUICommandFlow(self.ai_flow)
        
        # Set up TUI flow with widgets
        output_area = self.query_one("#output-area", TextArea)
        todo_list = self.query_one("#todo-list", ListView)
        status_label = self.query_one("#status-label", Label)
        self.tui_flow.set_widgets(output_area, todo_list, status_label)

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses"""
        if event.button.id == "execute-btn":
            await self.execute_goal()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission"""
        if event.input.id == "goal-input":
            await self.execute_goal()

    async def execute_goal(self):
        """Execute the user's goal"""
        goal_input = self.query_one("#goal-input", Input)
        goal = goal_input.value.strip()
        
        if not goal:
            self.query_one("#status-label", Label).text = "Please enter a goal"
            return
        
        self.query_one("#status-label", Label).text = "🔄 Executing..."
        
        try:
            await self.tui_flow.execute_user_goal(goal)
            self.query_one("#status-label", Label).text = "✅ Completed"
            
        except Exception as e:
            self.query_one("#status-label", Label).text = f"❌ Error: {str(e)}"

    def action_run_goal(self):
        """Run current goal"""
        asyncio.create_task(self.execute_goal())

    def action_cancel(self):
        """Cancel current execution"""
        if self.ai_flow:
            self.ai_flow.pause_automation()
            self.query_one("#status-label", Label).text = "⏸️ Paused"


# Main entry point
if __name__ == "__main__":
    app = AutomationTUI()
    app.run()