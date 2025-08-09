#!/usr/bin/env python3
"""
Terminal AI Agent
A simplified AI agent that can take tasks, create to-do lists, and execute commands in the terminal.
"""

import json
import re
import os
import sys
import argparse
import time
import logging
from dotenv import load_dotenv
import pty
import subprocess
import threading
import select
import termios
import fcntl
import struct
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, asdict
from enum import Enum
import requests

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ======================
# Configuration
# ======================

class CommandRisk(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    CRITICAL = "critical"

# ======================
# Safety Checker
# ======================

class AISafetyChecker:
    """Checks commands for safety and provides risk assessment"""
    
    DANGEROUS_PATTERNS = [
        (r'\brm\s+-rf\b', 'Recursive force delete'),
        (r'\brm\s+-rf\s*/', 'Delete root directory'),
        (r'\bchmod\s+777\b', 'World-writable permissions'),
        (r'\bchown\s+-R', 'Recursive ownership change'),
        (r'\bmkfs\b', 'Format filesystem'),
        (r'\bdd\b', 'Disk destroyer'),
        (r'\b>\s*/dev/sd', 'Overwrite disk'),
        (r'\bshutdown\s+-h\s+now', 'Immediate shutdown'),
        (r'\breboot\b', 'System reboot'),
        (r'\b:wq!\s*/etc', 'Force write system files'),
        (r'\bsudo\s+rm\b', 'Privileged delete'),
        (r'\bfind\s+.+\s+-delete\b', 'Find and delete'),
        (r'\bchmod\s+[0-7]777\b', 'Overly permissive'),
    ]
    
    CAUTION_PATTERNS = [
        (r'\brm\b', 'File deletion'),
        (r'\bchmod\b', 'Permission changes'),
        (r'\bchown\b', 'Ownership changes'),
        (r'\bmv\b', 'File movement'),
        (r'\bcp\b', 'File copying'),
        (r'\bscp\b', 'Remote copying'),
        (r'\bsudo\b', 'Privileged execution'),
        (r'\bapt-get\b', 'Package management'),
        (r'\byum\b', 'Package management'),
        (r'\bpip\b', 'Python package management'),
    ]
    
    @classmethod
    def assess_risk(cls, command: str) -> CommandRisk:
        """Assess the risk level of a command"""
        command_lower = command.lower()
        
        # Check for dangerous patterns
        for pattern, _ in cls.DANGEROUS_PATTERNS:
            if re.search(pattern, command_lower):
                return CommandRisk.CRITICAL
                
        # Check for caution patterns
        for pattern, _ in cls.CAUTION_PATTERNS:
            if re.search(pattern, command_lower):
                return CommandRisk.CAUTION
                
        return CommandRisk.SAFE
    
    @classmethod
    def get_warnings(cls, command: str) -> List[str]:
        """Get specific warnings for a command"""
        warnings = []
        command_lower = command.lower()
        
        for pattern, warning in cls.DANGEROUS_PATTERNS + cls.CAUTION_PATTERNS:
            if re.search(pattern, command_lower):
                warnings.append(f"Potential risk: {warning}")
                
        return warnings

# ======================
# Data Classes
# ======================

@dataclass
class CommandStep:
    command: str
    reasoning: str
    risk_level: CommandRisk
    expected_output: str
    alternatives: List[str] = None
    
    def __post_init__(self):
        if self.alternatives is None:
            self.alternatives = []

@dataclass
class PlanningResult:
    steps: List[CommandStep]
    overall_risk: CommandRisk
    requires_confirmation: bool
    estimated_time: str
    success_criteria: List[str]

@dataclass
class TodoItem:
    """Represents a single item in the to-do list"""
    id: int
    command: str
    reasoning: str
    risk_level: str
    status: str = "pending"  # pending, running, completed, failed
    output: str = ""

# ======================
# PTY Session Manager
# ======================

class PTYSession:
    """Manages a single persistent PTY session"""
    
    def __init__(self, session_id: str, shell: str = "/bin/bash"):
        self.session_id = session_id
        self.shell = shell
        self.master_fd = None
        self.slave_fd = None
        self.process = None
        self.is_running = False
        self.output_callbacks = []
        self.exit_callbacks = []
        self._output_thread = None
        self.output_buffer = ""
        
    def start(self) -> bool:
        """Start the PTY session"""
        try:
            # Create PTY
            self.master_fd, self.slave_fd = pty.openpty()
            
            # Start shell process
            self.process = subprocess.Popen(
                [self.shell],
                stdin=self.slave_fd,
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                preexec_fn=os.setsid
            )
            
            # Close slave fd in parent
            os.close(self.slave_fd)
            self.slave_fd = None
            
            self.is_running = True
            
            # Start output reading thread
            self._output_thread = threading.Thread(
                target=self._read_output,
                daemon=True
            )
            self._output_thread.start()
            
            logger.info(f"PTY session {self.session_id} started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start PTY session: {e}")
            self.cleanup()
            return False
    
    def _read_output(self):
        """Read output from PTY and notify callbacks"""
        while self.is_running and self.master_fd is not None:
            try:
                # Check if data is available
                if self.master_fd is not None:
                    ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                    
                    if ready:
                        if self.master_fd is not None:
                            data = os.read(self.master_fd, 1024)
                            if data:
                                decoded_data = data.decode('utf-8', errors='replace')
                                self.output_buffer += decoded_data
                                for callback in self.output_callbacks:
                                    callback(decoded_data)
                            else:
                                # EOF reached
                                break
                        
            except OSError:
                # PTY closed
                break
            except Exception as e:
                logger.error(f"Error reading output: {e}")
                break
        
        self.is_running = False
        for callback in self.exit_callbacks:
            callback()
    
    def execute_command(self, command: str) -> bool:
        """Execute a command in the PTY session"""
        if not self.is_running or self.master_fd is None:
            return False
        
        try:
            # Ensure command ends with newline
            if not command.endswith('\n'):
                command += '\n'
            
            if self.master_fd is not None:
                os.write(self.master_fd, command.encode('utf-8'))
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to execute command: {e}")
            return False
    
    def send_control_character(self, char: str) -> bool:
        """Send control character (e.g., Ctrl+C)"""
        if not self.is_running or self.master_fd is None:
            return False
        
        try:
            # Convert Ctrl+C to actual control character
            if char.upper() == 'C':
                control_char = b'\x03'  # ETX (End of Text) - Ctrl+C
            elif char.upper() == 'D':
                control_char = b'\x04'  # EOT (End of Transmission) - Ctrl+D
            elif char.upper() == 'Z':
                control_char = b'\x1a'  # SUB (Substitute) - Ctrl+Z
            else:
                return False
            
            if self.master_fd is not None:
                os.write(self.master_fd, control_char)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to send control character: {e}")
            return False
    
    def resize(self, rows: int, cols: int) -> bool:
        """Resize the PTY terminal"""
        if not self.is_running or self.master_fd is None:
            return False
        
        try:
            # Use TIOCSWINSZ to set window size
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            if self.master_fd is not None:
                fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
                return True
            return False
            
        except Exception as e:
            logger.error(f"Failed to resize PTY: {e}")
            return False
    
    def add_output_callback(self, callback):
        """Add callback for output data"""
        self.output_callbacks.append(callback)
    
    def add_exit_callback(self, callback):
        """Add callback for session exit"""
        self.exit_callbacks.append(callback)
    
    def cleanup(self):
        """Clean up resources"""
        self.is_running = False
        
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except:
                pass
            self.master_fd = None
        
        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except:
                pass
            self.slave_fd = None
        
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        
        logger.info(f"PTY session {self.session_id} cleaned up")

class PTYManager:
    """Manages multiple PTY sessions"""
    
    def __init__(self):
        self.sessions = {}
        self.lock = threading.Lock()
    
    def create_session(self, session_id: str, shell: str = "/bin/bash") -> bool:
        """Create a new PTY session"""
        with self.lock:
            if session_id in self.sessions:
                return False
            
            session = PTYSession(session_id, shell)
            if session.start():
                self.sessions[session_id] = session
                return True
            return False
    
    def get_session(self, session_id: str):
        """Get a PTY session by ID"""
        with self.lock:
            return self.sessions.get(session_id)
    
    def execute_command(self, session_id: str, command: str) -> bool:
        """Execute command in specified session"""
        session = self.get_session(session_id)
        if session:
            return session.execute_command(command)
        return False
    
    def send_control(self, session_id: str, char: str) -> bool:
        """Send control character to session"""
        session = self.get_session(session_id)
        if session:
            return session.send_control_character(char)
        return False
    
    def resize_session(self, session_id: str, rows: int, cols: int) -> bool:
        """Resize a session's terminal"""
        session = self.get_session(session_id)
        if session:
            return session.resize(rows, cols)
        return False
    
    def close_session(self, session_id: str) -> bool:
        """Close a PTY session"""
        with self.lock:
            session = self.sessions.pop(session_id, None)
            if session:
                session.cleanup()
                return True
            return False
    
    def list_sessions(self) -> list:
        """List all active session IDs"""
        return list(self.sessions.keys())
    
    def cleanup_all(self):
        """Clean up all sessions"""
        with self.lock:
            for session in self.sessions.values():
                session.cleanup()
            self.sessions.clear()

# Global manager instance
manager = PTYManager()
# ======================
# AI Command Planner
# ======================

class OpenAIPlanner:
    """Uses OpenAI API to generate command plans"""
    
    def __init__(self, api_key: str, base_url: str = None, model: str = None):
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = model or "gpt-3.5-turbo"
        
    def generate_plan(self, user_request: str, context: Dict[str, Any] = None) -> PlanningResult:
        """Generate a command plan from natural language"""
        context = context or {}
        
        prompt = self._build_prompt(user_request, context)
        
        try:
            response = self._call_openai(prompt)
            return self._parse_response(response)
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            return self._fallback_plan(user_request)
    
    def _build_prompt(self, user_request: str, context: Dict[str, Any]) -> str:
        """Build the prompt for OpenAI"""
        return f"""
You are a helpful AI assistant that converts natural language requests into safe shell commands.
Current directory: {context.get('cwd', os.getcwd())}
User request: {user_request}

Generate a step-by-step plan with:
1. Each command to execute
2. Reasoning for each command
3. Expected output
4. Risk assessment (safe/caution/dangerous/critical)
5. Alternative safer commands if applicable

Format as JSON:
{{
    "steps": [
        {{
            "command": "command to run",
            "reasoning": "why this command",
            "risk_level": "safe|caution|dangerous|critical",
            "expected_output": "what to expect",
            "alternatives": ["safer option 1", "safer option 2"]
        }}
    ],
    "overall_risk": "safe|caution|dangerous|critical",
    "requires_confirmation": true|false,
    "estimated_time": "time estimate",
    "success_criteria": ["criteria1", "criteria2"]
}}
"""
    
    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        data = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.3,
            "max_tokens": 1000
        }
        
        response = requests.post(
            f"{self.base_url}/chat/completions",
            headers=headers,
            json=data,
            timeout=30
        )
        
        response.raise_for_status()
        
        # Check if response is empty
        if not response.text.strip():
            raise requests.RequestException("Empty response from API")
        
        try:
            return response.json()["choices"][0]["message"]["content"]
        except (KeyError, ValueError) as e:
            raise requests.RequestException(f"Invalid JSON response from API: {e}")
    
    def _parse_response(self, response: str) -> PlanningResult:
        """Parse OpenAI response into PlanningResult"""
        try:
            data = json.loads(response)
            
            steps = []
            for step_data in data["steps"]:
                step = CommandStep(
                    command=step_data["command"],
                    reasoning=step_data["reasoning"],
                    risk_level=CommandRisk(step_data["risk_level"]),
                    expected_output=step_data["expected_output"],
                    alternatives=step_data.get("alternatives", [])
                )
                steps.append(step)
            
            # Override risk if any step is dangerous
            risk_values = ["safe", "caution", "dangerous", "critical"]
            max_risk = max(steps, key=lambda s: risk_values.index(s.risk_level.value))
            overall_risk = max_risk.risk_level
            
            requires_confirmation = any(step.risk_level in [CommandRisk.DANGEROUS, CommandRisk.CRITICAL] for step in steps)
            
            return PlanningResult(
                steps=steps,
                overall_risk=overall_risk,
                requires_confirmation=requires_confirmation,
                estimated_time=data.get("estimated_time", "unknown"),
                success_criteria=data.get("success_criteria", [])
            )
            
        except Exception as e:
            logger.error(f"Error parsing response: {e}")
            # Re-raise the exception so it's caught in generate_plan which has the user request
            raise
    
    def _fallback_plan(self, user_request: str) -> PlanningResult:
        """Generate a fallback plan when OpenAI fails"""
        # Try to parse simple commands locally
        commands = self._parse_simple_commands(user_request)
        
        if commands:
            steps = []
            for command in commands:
                steps.append(CommandStep(
                    command=command,
                    reasoning="Parsed from user request when AI API unavailable",
                    risk_level=CommandRisk.SAFE,
                    expected_output="Command executed successfully"
                ))
            return PlanningResult(
                steps=steps,
                overall_risk=CommandRisk.SAFE,
                requires_confirmation=False,
                estimated_time="immediate",
                success_criteria=[f"Successfully executed: {', '.join(commands)}"]
            )
        else:
            # Fallback to generic message if parsing fails
            return PlanningResult(
                steps=[CommandStep(
                    command="echo 'Please provide more specific instructions'",
                    reasoning="Fallback due to API error and unable to parse locally",
                    risk_level=CommandRisk.SAFE,
                    expected_output="User guidance message"
                )],
                overall_risk=CommandRisk.SAFE,
                requires_confirmation=False,
                estimated_time="immediate",
                success_criteria=["User provides clearer instructions"]
            )
    
    def _parse_simple_commands(self, user_request: str) -> List[str]:
        """Parse simple commands from user request when AI is unavailable"""
        request_lower = user_request.lower().strip()
        logger.info(f"Parsing user request: {user_request}")
        commands = []
        
        # Handle directory creation with full path support
        # Look for patterns like "make a dir named project/src"
        dir_patterns = [
            r'(?:make a dir|create a directory)\s+(?:named|called)\s+([a-zA-Z0-9/_\-\.]+)',
        ]
        
        # Also handle the case where directories are listed with "and make a dir"
        # Split the request to handle multiple directory creation commands
        import re
        
        # Find all directory creation commands
        dir_pattern = r'(?:make a dir|create a directory)\s+(?:named|called)\s+([a-zA-Z0-9/_\-\.]+)'
        dir_matches = re.findall(dir_pattern, request_lower)
        
        # Remove duplicates and filter out "named" which is a false positive
        seen = set()
        for dir_path in dir_matches:
            if dir_path != "named" and dir_path not in seen:
                seen.add(dir_path)
                logger.info(f"Found directory path: {dir_path}")
                commands.append(f"mkdir -p {dir_path}")
        
        # Handle file creation with extension and full path support
        # Look for patterns like "make a txt file named project/README.md"
        file_pattern = r'make a (\w+) file (?:named|called) ([a-zA-Z0-9/_\-\.]+\.\w+)'
        file_matches = re.findall(file_pattern, request_lower)
        
        for ext, file_path in file_matches:
            # Don't modify the extension if it's already correct
            if not file_path.endswith(f'.{ext}'):
                file_path = f"{file_path}.{ext}"
            logger.info(f"Found file path: {file_path}")
            commands.append(f"touch {file_path}")
        
        # Handle generic file creation without extension specification
        generic_file_pattern = r'make a file (?:named|called) ([a-zA-Z0-9/_\-\.]+\.\w+)'
        generic_matches = re.findall(generic_file_pattern, request_lower)
        for file_path in generic_matches:
            logger.info(f"Found generic file path: {file_path}")
            commands.append(f"touch {file_path}")
        
        # Handle writing content to file
        content_matches = re.findall(r"(?:file (?:named|called) ([a-zA-Z0-9/_\-\.]+\.\w+)|([a-zA-Z0-9/_\-\.]+\.\w+))\s+with\s+'([^']+)'", request_lower)
        for match in content_matches:
            file_name = match[0] if match[0] else match[1]
            content = match[2]
            if file_name:
                logger.info(f"Found file name: {file_name} with content: {content}")
                commands.append(f"echo '{content}' > {file_name}")
        
        # Handle directory listing
        if "list files" in request_lower or "ls" in request_lower:
            commands.append("ls")
        
        # Handle directory change
        if "change directory" in request_lower or "cd" in request_lower:
            match = re.search(r'(?:to|into)\s+(\S+)', request_lower)
            if match:
                dir_name = match.group(1)
                commands.append(f"cd {dir_name}")
        
        # Handle file copying
        if "copy file" in request_lower or "cp" in request_lower:
            commands.append("cp source_file destination_file")
        
        # Handle file moving
        if "move file" in request_lower or "mv" in request_lower:
            commands.append("mv source_file destination_file")
        
        # Handle file deletion
        if "delete file" in request_lower or "remove file" in request_lower or "rm" in request_lower:
            commands.append("rm filename")
        
        # If no commands were parsed, return default mkdir command
        if not commands:
            logger.info("No specific commands found, using default mkdir")
            commands.append("mkdir new_directory")
        
        return commands

class CommandExecutor:
    """Executes commands with safety checks and feedback"""
    
    def __init__(self, pty_manager):
        self.pty_manager = pty_manager
    
    def create_session(self, session_id: str) -> bool:
        """Create a new PTY session"""
        return self.pty_manager.create_session(session_id)
    
    def execute_plan(self, plan: PlanningResult, session_id: str) -> List[Dict[str, Any]]:
        """Execute a command plan step by step"""
        results = []
        
        for i, step in enumerate(plan.steps):
            logger.info(f"Executing step {i+1}: {step.command}")
            
            # Safety check
            risk = AISafetyChecker.assess_risk(step.command)
            warnings = AISafetyChecker.get_warnings(step.command)
            
            result = {
                "step": i + 1,
                "command": step.command,
                "reasoning": step.reasoning,
                "risk_level": risk.value,
                "warnings": warnings,
                "success": False,
                "output": ""
            }
            
            # Use subprocess for reliable command execution instead of PTY
            try:
                import subprocess
                completed_process = subprocess.run(
                    step.command,
                    shell=True,
                    capture_output=True,
                    text=True,
                    timeout=10
                )
                
                if completed_process.returncode == 0:
                    result["success"] = True
                    output = completed_process.stdout.strip()
                    if output:
                        result["output"] = output
                    else:
                        result["output"] = "Command executed successfully"
                else:
                    result["success"] = False
                    error_output = completed_process.stderr.strip()
                    if error_output:
                        result["output"] = f"Command failed: {error_output}"
                    else:
                        result["output"] = "Command failed with non-zero exit code"
                        
            except subprocess.TimeoutExpired:
                result["output"] = "Command timed out"
            except Exception as e:
                result["output"] = f"Failed to execute command: {str(e)}"
            
            results.append(result)
            
        return results

class AICommandPlanner:
    """Main AI command planner that combines OpenAI planning with execution"""
    
    def __init__(self, api_key: str, base_url: str = None, model: str = None):
        self.planner = OpenAIPlanner(api_key, base_url, model)
        self.executor = CommandExecutor(manager)
    
    def set_pty_manager(self, pty_manager):
        """Set the PTY manager for command execution"""
        self.executor.pty_manager = pty_manager

# ======================
# Planning Loop
# ======================

class PlanningLoop:
    """Main planning loop that iterates until goals are achieved"""
    
    def __init__(self, ai_planner: AICommandPlanner):
        self.planner = ai_planner
        self.max_iterations = 10
        self.retry_delay = 2
        
    def execute_goal(self, goal: str, session_id: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Execute a goal through iterative planning and execution"""
        context = context or {}
        iteration = 0
        results = []
        
        logger.info(f"Starting execution of goal: {goal}")
        
        while iteration < self.max_iterations:
            logger.info(f"Iteration {iteration + 1}")
            
            # Generate plan
            try:
                plan = self.planner.planner.generate_plan(goal, context)
            except Exception as e:
                logger.error(f"Failed to generate plan: {e}")
                return {
                    "status": "planning_failed",
                    "error": str(e),
                    "iteration": iteration
                }
            
            # Check if confirmation needed
            if plan.requires_confirmation:
                return {
                    "status": "confirmation_required",
                    "plan": self._plan_to_dict(plan),
                    "message": "Dangerous commands detected. Please review and confirm.",
                    "iteration": iteration
                }
            
            # Execute plan
            try:
                execution_results = self.planner.executor.execute_plan(plan, session_id)
            except Exception as e:
                logger.error(f"Failed to execute plan: {e}")
                return {
                    "status": "execution_failed",
                    "error": str(e),
                    "iteration": iteration
                }
            results.extend(execution_results)
            
            # Check if goal is achieved
            if self._check_goal_achievement(goal, execution_results, context):
                return {
                    "status": "success",
                    "results": results,
                    "iterations": iteration + 1,
                    "final_context": context
                }
            
            # Check for failures
            failed_steps = [r for r in execution_results if not r.get("success", False)]
            if failed_steps:
                logger.warning(f"Failed steps detected: {len(failed_steps)}")
                
                # Adjust context for retry
                context = self._adjust_context_for_retry(goal, execution_results, context)
                
                # Wait before retry
                time.sleep(self.retry_delay)
            
            iteration += 1
        
        return {
            "status": "max_iterations_reached",
            "results": results,
            "iterations": iteration,
            "message": "Maximum iterations reached without achieving goal"
        }
    
    def _check_goal_achievement(self, goal: str, results: List[Dict[str, Any]], context: Dict[str, Any]) -> bool:
        """Check if the goal has been achieved based on results"""
        # Simple heuristic - if all commands succeeded, assume goal achieved
        # In a real implementation, this would use AI to analyze outputs
        return all(r.get("success", False) for r in results)
    
    def _adjust_context_for_retry(self, goal: str, results: List[Dict[str, Any]], context: Dict[str, Any]) -> Dict[str, Any]:
        """Adjust context based on failed execution"""
        # Update context with failure information
        failed_steps = [r for r in results if not r.get("success", False)]
        
        context["previous_failures"] = failed_steps
        context["retry_count"] = context.get("retry_count", 0) + 1
        
        # Add specific error information
        if failed_steps:
            context["last_error"] = failed_steps[-1].get("output", "Unknown error")
        
        return context
    
    def _plan_to_dict(self, plan: PlanningResult) -> Dict[str, Any]:
        """Convert plan to dictionary for JSON serialization"""
        return {
            "steps": [
                {
                    "command": step.command,
                    "reasoning": step.reasoning,
                    "risk_level": step.risk_level.value,
                    "expected_output": step.expected_output,
                    "alternatives": step.alternatives
                }
                for step in plan.steps
            ],
            "overall_risk": plan.overall_risk.value,
            "requires_confirmation": plan.requires_confirmation,
            "estimated_time": plan.estimated_time,
            "success_criteria": plan.success_criteria
        }

# ======================
# Terminal AI Agent
# ======================

class TerminalAIAgent:
    """Main Terminal AI Agent that orchestrates planning and execution"""
    
    def __init__(self, api_key: str = None, base_url: str = None, model: str = None):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "mock-key")
        self.base_url = base_url or os.getenv("OPENAI_BASE_URL")
        self.model = model or os.getenv("AI_MODEL")
        self.planner = AICommandPlanner(self.api_key, self.base_url, self.model)
        self.todo_list: List[TodoItem] = []
        self.session_id = "terminal-ai-agent"
        
        # Create PTY session
        if not manager.get_session(self.session_id):
            manager.create_session(self.session_id)
    
    def create_todo_list(self, goal: str) -> List[TodoItem]:
        """Create a to-do list from a natural language goal"""
        try:
            # Generate plan using AI
            plan = self.planner.planner.generate_plan(goal)
            
            # Convert plan to todo items
            self.todo_list = []
            for i, step in enumerate(plan.steps):
                todo_item = TodoItem(
                    id=i + 1,
                    command=step.command,
                    reasoning=step.reasoning,
                    risk_level=step.risk_level.value,
                    status="pending"
                )
                self.todo_list.append(todo_item)
            
            return self.todo_list
            
        except Exception as e:
            logger.error(f"Failed to create to-do list: {e}")
            # Create a fallback todo item
            fallback_item = TodoItem(
                id=1,
                command="echo 'Failed to generate plan. Please try again.'",
                reasoning="Fallback due to error",
                risk_level="safe",
                status="pending"
            )
            self.todo_list = [fallback_item]
            return self.todo_list
    
    def update_todo_list(self, item_id: int, status: str, output: str = ""):
        """Update a todo item's status and output"""
        for item in self.todo_list:
            if item.id == item_id:
                item.status = status
                item.output = output
                break
    
    def execute_todo_list(self) -> List[Dict[str, Any]]:
        """Execute all items in the to-do list"""
        results = []
        
        # Create a plan from the todo list
        steps = []
        for item in self.todo_list:
            step = CommandStep(
                command=item.command,
                reasoning=item.reasoning,
                risk_level=CommandRisk(item.risk_level),
                expected_output="",
                alternatives=[]
            )
            steps.append(step)
        
        plan = PlanningResult(
            steps=steps,
            overall_risk=CommandRisk.SAFE,
            requires_confirmation=False,
            estimated_time="unknown",
            success_criteria=[]
        )
        
        # Execute the plan
        execution_results = self.planner.executor.execute_plan(plan, self.session_id)
        
        # Update todo list with results
        for i, result in enumerate(execution_results):
            if i < len(self.todo_list):
                item_id = self.todo_list[i].id
                status = "completed" if result.get("success") else "failed"
                output = result.get("output", "")
                self.update_todo_list(item_id, status, output)
        
        return execution_results
    
    def run_task(self, goal: str) -> Dict[str, Any]:
        """Run a complete task from goal to execution"""
        print(f"🎯 Goal: {goal}")
        print("=" * 50)
        
        # Create to-do list
        print("\n📋 Creating to-do list...")
        self.create_todo_list(goal)
        
        # Display to-do list
        print("\n📝 To-Do List:")
        for item in self.todo_list:
            risk_icon = {
                "safe": "✅",
                "caution": "⚠️",
                "dangerous": "🚨",
                "critical": "💀"
            }.get(item.risk_level, "❓")
            print(f"  {item.id}. {risk_icon} {item.command}")
            print(f"     Reasoning: {item.reasoning}")
            print()
        
        # Check for dangerous commands
        dangerous_items = [item for item in self.todo_list if item.risk_level in ["dangerous", "critical"]]
        if dangerous_items:
            print("⚠️  WARNING: This plan contains potentially dangerous commands!")
            response = input("\nDo you want to continue? (y/N): ")
            if response.lower() != 'y':
                return {"status": "cancelled", "message": "User cancelled execution"}
        
        # Execute to-do list
        print("\n🚀 Executing to-do list...")
        results = self.execute_todo_list()
        
        # Display results
        print("\n📊 Execution Results:")
        for item in self.todo_list:
            icon = "✅" if item.status == "completed" else "❌" if item.status == "failed" else "⏳"
            print(f"  {icon} {item.command}")
            if item.output:
                print(f"     Output: {item.output}")
        
        success_count = sum(1 for item in self.todo_list if item.status == "completed")
        total_count = len(self.todo_list)
        print(f"\n✅ Completed {success_count}/{total_count} tasks")
        
        return {
            "status": "completed" if success_count == total_count else "partial",
            "results": results,
            "todo_list": [asdict(item) for item in self.todo_list]
        }

# ======================
# Main Entry Point
# ======================

def main():
    """Main entry point for the Terminal AI Agent"""
    # Load environment variables
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="Terminal AI Agent")
    parser.add_argument("--api-key", help="OpenAI API key", default=os.getenv("OPENAI_API_KEY"))
    parser.add_argument("--base-url", help="OpenAI API base URL", default=os.getenv("OPENAI_BASE_URL"))
    parser.add_argument("--model", help="AI model to use", default=os.getenv("AI_MODEL"))
    parser.add_argument("--goal", help="Goal to execute", required=True)
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("Error: OpenAI API key required. Set OPENAI_API_KEY environment variable or use --api-key")
        sys.exit(1)
    
    # Create and run agent
    agent = TerminalAIAgent(args.api_key, args.base_url, args.model)
    
    try:
        result = agent.run_task(args.goal)
        print(json.dumps(result, indent=2, default=str))
    except KeyboardInterrupt:
        print("\nExecution cancelled by user")
    finally:
        manager.close_session(agent.session_id)

if __name__ == "__main__":
    main()