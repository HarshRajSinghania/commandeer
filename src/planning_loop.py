#!/usr/bin/env python3
"""
Iterative Planning Loop
Implements the loop that reviews command outputs and adjusts plans
"""

import json
import time
from typing import Dict, List, Any, Optional
import logging
from ai_planner import AICommandPlanner, PlanningResult, CommandStep
from pty_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
            plan = self.planner.planner.generate_plan(goal, context)
            
            # Check if confirmation needed
            if plan.requires_confirmation:
                return {
                    "status": "confirmation_required",
                    "plan": self._plan_to_dict(plan),
                    "message": "Dangerous commands detected. Please review and confirm.",
                    "iteration": iteration
                }
            
            # Execute plan
            execution_results = self.planner.executor.execute_plan(plan, session_id)
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


class InteractivePlanner:
    """Interactive command planning with user feedback"""
    
    def __init__(self, ai_planner: AICommandPlanner):
        self.planner = ai_planner
        self.planning_loop = PlanningLoop(ai_planner)
    
    def interactive_execute(self, goal: str, session_id: str) -> Dict[str, Any]:
        """Interactive execution with user confirmation"""
        print(f"\n🎯 Goal: {goal}")
        print("-" * 50)
        
        # Generate initial plan
        plan = self.planner.planner.generate_plan(goal)
        
        # Display plan
        self._display_plan(plan)
        
        # Check if confirmation needed
        if plan.requires_confirmation:
            if not self._get_user_confirmation(plan):
                return {"status": "cancelled", "message": "User cancelled execution"}
        
        # Execute with loop
        result = self.planning_loop.execute_goal(goal, session_id)
        
        # Display results
        self._display_results(result)
        
        return result
    
    def _display_plan(self, plan: PlanningResult):
        """Display the plan to the user"""
        print("\n📋 Execution Plan:")
        for i, step in enumerate(plan.steps, 1):
            risk_icon = self._get_risk_icon(step.risk_level)
            print(f"{i}. {risk_icon} {step.command}")
            print(f"   Reasoning: {step.reasoning}")
            print(f"   Risk: {step.risk_level.value}")
            if step.alternatives:
                print(f"   Alternatives: {', '.join(step.alternatives)}")
            print()
    
    def _get_risk_icon(self, risk: CommandRisk) -> str:
        """Get emoji for risk level"""
        icons = {
            CommandRisk.SAFE: "✅",
            CommandRisk.CAUTION: "⚠️",
            CommandRisk.DANGEROUS: "🚨",
            CommandRisk.CRITICAL: "💀"
        }
        return icons.get(risk, "❓")
    
    def _get_user_confirmation(self, plan: PlanningResult) -> bool:
        """Get user confirmation for dangerous commands"""
        print("\n⚠️  WARNING: This plan contains potentially dangerous commands!")
        print("Commands requiring confirmation:")
        
        for step in plan.steps:
            if step.risk_level in [CommandRisk.DANGEROUS, CommandRisk.CRITICAL]:
                print(f"  - {step.command} ({step.risk_level.value})")
        
        response = input("\nDo you want to continue? (y/N): ")
        return response.lower() == 'y'
    
    def _display_results(self, result: Dict[str, Any]):
        """Display execution results"""
        print("\n📊 Execution Results:")
        print(f"Status: {result['status']}")
        
        if 'results' in result:
            for r in result['results']:
                icon = "✅" if r.get('success') else "❌"
                print(f"{icon} {r['command']}")
                if r.get('output'):
                    print(f"   Output: {r['output']}")


# Example usage
if __name__ == "__main__":
    import os
    
    # Setup
    api_key = os.getenv("OPENAI_API_KEY", "your-api-key")
    planner = AICommandPlanner(api_key)
    planner.set_pty_manager(manager)
    
    # Create session
    manager.create_session("interactive")
    
    # Interactive execution
    interactive = InteractivePlanner(planner)
    
    # Test with a simple goal
    result = interactive.interactive_execute(
        "create a new directory called 'test-project' and initialize a git repository",
        "interactive"
    )
    
    print(json.dumps(result, indent=2, default=str))