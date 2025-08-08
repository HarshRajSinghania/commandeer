#!/usr/bin/env python3
"""
Command Execution Flow
Implements AI-driven automation with queued command execution and streaming output
"""

import asyncio
import json
import time
import os
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from textual.widgets import TextArea, ListView, ListItem, Label
from textual.reactive import reactive
from textual.message import Message
import threading
import queue

from ai_planner import AICommandPlanner, PlanningResult, CommandStep
from pty_manager import manager


@dataclass
class CommandTask:
    """Represents a single command task"""
    id: str
    command: str
    reasoning: str
    expected_output: str
    status: str = "pending"  # pending, running, completed, failed
    actual_output: str = ""
    exit_code: Optional[int] = None
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    retry_count: int = 0

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CommandQueue:
    """Manages command queue for sequential execution"""
    
    def __init__(self):
        self.queue: List[CommandTask] = []
        self.current_task: Optional[CommandTask] = None
        self.completed_tasks: List[CommandTask] = []
        self.lock = threading.Lock()
    
    def add_task(self, task: CommandTask):
        """Add a task to the queue"""
        with self.lock:
            self.queue.append(task)
    
    def get_next_task(self) -> Optional[CommandTask]:
        """Get the next task from queue"""
        with self.lock:
            if self.queue:
                self.current_task = self.queue.pop(0)
                return self.current_task
            return None
    
    def mark_completed(self, task: CommandTask):
        """Mark a task as completed"""
        with self.lock:
            self.completed_tasks.append(task)
            if self.current_task == task:
                self.current_task = None
    
    def get_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        with self.lock:
            return {
                "pending": len(self.queue),
                "completed": len(self.completed_tasks),
                "current": self.current_task.to_dict() if self.current_task else None
            }


class CommandExecutor:
    """Executes commands with streaming output"""
    
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.output_callbacks = []
        self.is_running = False
    
    def add_output_callback(self, callback):
        """Add callback for output streaming"""
        self.output_callbacks.append(callback)
    
    def execute_command(self, command: str) -> bool:
        """Execute a single command"""
        return manager.execute_command(self.session_id, command)
    
    def get_output(self) -> str:
        """Get current output from session"""
        # This would integrate with the PTY output streaming
        return "Command output would be streamed here"


class AICommandFlow:
    """Main command execution flow with AI automation"""
    
    def __init__(self, api_key: str, base_url: str = None, model: str = None):
        self.planner = AICommandPlanner(api_key, base_url, model)
        self.queue = CommandQueue()
        self.executor = None
        self.current_goal = ""
        self.is_automating = False
        
    def set_session(self, session_id: str):
        """Set the PTY session"""
        self.executor = CommandExecutor(session_id)
        self.planner.set_pty_manager(manager)
    
    async def execute_goal(self, goal: str, on_update=None) -> Dict[str, Any]:
        """Execute a complete goal with AI automation"""
        self.current_goal = goal
        self.is_automating = True
        
        # Create session if needed
        if not manager.get_session("flow-session"):
            manager.create_session("flow-session")
            self.set_session("flow-session")
        
        # Generate initial plan
        plan = self.planner.planner.generate_plan(goal)
        
        # Convert plan to tasks
        for i, step in enumerate(plan.steps):
            task = CommandTask(
                id=f"task_{i+1}",
                command=step.command,
                reasoning=step.reasoning,
                expected_output=step.expected_output,
                status="pending"
            )
            self.queue.add_task(task)
        
        # Execute tasks sequentially
        results = []
        while True:
            task = self.queue.get_next_task()
            if not task:
                break
            
            # Execute task
            task.status = "running"
            task.start_time = time.time()
            
            success = self.executor.execute_command(task.command)
            task.end_time = time.time()
            
            if success:
                task.status = "completed"
                task.actual_output = "Command executed successfully"
            else:
                task.status = "failed"
                task.actual_output = "Command failed"
            
            self.queue.mark_completed(task)
            results.append(task.to_dict())
            
            # Check if we need to adjust the plan
            if task.status == "failed":
                # AI could adjust the plan here
                pass
            
            # Notify UI of update
            if on_update:
                on_update({
                    "current_task": task.to_dict(),
                    "queue_status": self.queue.get_status(),
                    "results": results
                })
        
        self.is_automating = False
        return {
            "status": "completed",
            "goal": goal,
            "results": results,
            "queue_status": self.queue.get_status()
        }
    
    def get_queue_status(self) -> Dict[str, Any]:
        """Get current queue status"""
        return self.queue.get_status()
    
    def pause_automation(self):
        """Pause the automation"""
        self.is_automating = False
    
    def resume_automation(self):
        """Resume the automation"""
        self.is_automating = True
    
    def clear_queue(self):
        """Clear all pending tasks"""
        self.queue.queue.clear()


class TUICommandFlow:
    """TUI integration for command flow"""
    
    def __init__(self, ai_flow: AICommandFlow):
        self.ai_flow = ai_flow
        self.output_area = None
        self.todo_list = None
        self.status_label = None
    
    def set_widgets(self, output_area, todo_list, status_label):
        """Set TUI widgets"""
        self.output_area = output_area
        self.todo_list = todo_list
        self.status_label = status_label
    
    async def execute_user_goal(self, goal: str):
        """Execute user goal with TUI updates"""
        def on_update(data):
            if self.output_area:
                self.output_area.text = json.dumps(data, indent=2)
            if self.status_label:
                self.status_label.text = f"Executing: {data['current_task']['command']}"
        
        result = await self.ai_flow.execute_goal(goal, on_update)
        
        if self.output_area:
            self.output_area.text = json.dumps(result, indent=2)
        
        return result
    
    def update_todo_display(self):
        """Update the todo list display"""
        if not self.todo_list:
            return
        
        status = self.ai_flow.get_queue_status()
        items = []
        
        for task in self.ai_flow.queue.completed_tasks:
            items.append(ListItem(Label(f"✅ {task.command}")))
        
        for task in self.ai_flow.queue.queue:
            items.append(ListItem(Label(f"⏳ {task.command}")))
        
        if self.ai_flow.queue.current_task:
            items.append(ListItem(Label(f"🔄 {self.ai_flow.queue.current_task.command}")))
        
        self.todo_list.clear()
        self.todo_list.extend(items)


# Example usage
if __name__ == "__main__":
    import asyncio
    
    # Setup
    api_key = "your-api-key-here"
    base_url = "https://samuraiapi.in/v1/"
    model = "gpt-4"
    
    flow = AICommandFlow(api_key, base_url, model)
    flow.set_session("demo-session")
    
    # Test execution
    async def test():
        result = await flow.execute_goal("create a new directory called 'test-project' and initialize git")
        print(json.dumps(result, indent=2))
    
    asyncio.run(test())