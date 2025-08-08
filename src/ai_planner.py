#!/usr/bin/env python3
"""
AI Command Planning Layer
Takes natural language requests and generates safe shell commands with reasoning
"""

import json
import re
import os
import sys
from typing import List, Dict, Any, Optional
import requests
import logging
from dataclasses import dataclass
from enum import Enum

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class CommandRisk(Enum):
    SAFE = "safe"
    CAUTION = "caution"
    DANGEROUS = "dangerous"
    CRITICAL = "critical"


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


class OpenAIPlanner:
    """Uses OpenAI API to generate command plans"""
    
    def __init__(self, api_key: str, base_url: str = None):
        self.api_key = api_key
        self.base_url = base_url or "https://api.openai.com/v1"
        self.model = "gpt-3.5-turbo"
        
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
        return response.json()["choices"][0]["message"]["content"]
    
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
            max_risk = max(steps, key=lambda s: ["safe", "caution", "dangerous", "critical"].index(s.risk_level.value))
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
            return self._fallback_plan("fallback")
    
    def _fallback_plan(self, user_request: str) -> PlanningResult:
        """Generate a fallback plan when OpenAI fails"""
        return PlanningResult(
            steps=[CommandStep(
                command="echo 'Please provide more specific instructions'",
                reasoning="Fallback due to API error",
                risk_level=CommandRisk.SAFE,
                expected_output="User guidance message"
            )],
            overall_risk=CommandRisk.SAFE,
            requires_confirmation=False,
            estimated_time="immediate",
            success_criteria=["User provides clearer instructions"]
        )


class CommandExecutor:
    """Executes commands with safety checks and feedback"""
    
    def __init__(self, pty_manager):
        self.pty_manager = pty_manager
        self.current_session = None
    
    def create_session(self, session_id: str) -> bool:
        """Create a new PTY session"""
        return self.pty_manager.create_session(session_id)
    
    def execute_plan(self, plan: PlanningResult, session_id: str) -> List[Dict[str, Any]]:
        """Execute a command plan step by step"""
        results = []
        
        if not self.pty_manager.get_session(session_id):
            self.create_session(session_id)
        
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
                "output": "",
                "success": False
            }
            
            # Execute command
            try:
                success = self.pty_manager.execute_command(session_id, step.command)
                if success:
                    result["success"] = True
                    result["output"] = "Command executed successfully"
                else:
                    result["output"] = "Failed to execute command"
                    
            except Exception as e:
                result["output"] = str(e)
                
            results.append(result)
            
            # Check success criteria
            if not result["success"]:
                logger.warning(f"Step {i+1} failed, stopping execution")
                break
                
        return results


class AICommandPlanner:
    """Main orchestrator for AI command planning"""
    
    def __init__(self, api_key: str, base_url: str = None):
        self.planner = OpenAIPlanner(api_key, base_url)
        self.executor = None
    
    def set_pty_manager(self, pty_manager):
        """Set the PTY manager for execution"""
        self.executor = CommandExecutor(pty_manager)
    
    def plan_and_execute(self, user_request: str, session_id: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """Complete planning and execution workflow"""
        if not self.executor:
            raise ValueError("PTY manager not set")
            
        # Generate plan
        plan = self.planner.generate_plan(user_request, context)
        
        # Check if confirmation needed
        if plan.requires_confirmation:
            return {
                "status": "confirmation_required",
                "plan": plan,
                "message": "Dangerous commands detected. Please review and confirm."
            }
        
        # Execute plan
        results = self.executor.execute_plan(plan, session_id)
        
        return {
            "status": "completed",
            "plan": plan,
            "results": results
        }


if __name__ == "__main__":
    # Example usage
    import os
    
    api_key = os.getenv("OPENAI_API_KEY", "your-api-key")
    planner = AICommandPlanner(api_key)
    
    # Test with a simple request
    result = planner.planner.generate_plan("create a new directory called 'test'")
    print(json.dumps(result.__dict__, indent=2, default=str))