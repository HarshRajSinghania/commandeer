#!/usr/bin/env python3
"""
AI Command Planning Main Entry Point
Integrates AI planning with PTY backend
"""

import os
import sys
import argparse
import json
from src.ai_planner import AICommandPlanner, AISafetyChecker
from src.planning_loop import InteractivePlanner, PlanningLoop
from pty_manager import manager

def main():
    """Main entry point for AI command planning"""
    parser = argparse.ArgumentParser(description="AI Command Planning Layer")
    parser.add_argument("--api-key", help="OpenAI API key", default=os.getenv("OPENAI_API_KEY"))
    parser.add_argument("--base-url", help="OpenAI API base URL", default=os.getenv("OPENAI_BASE_URL"))
    parser.add_argument("--session", help="Session ID", default="ai-session")
    parser.add_argument("--goal", help="Goal to execute", required=True)
    parser.add_argument("--interactive", action="store_true", help="Interactive mode")
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("Error: OpenAI API key required. Set OPENAI_API_KEY environment variable or use --api-key")
        sys.exit(1)
    
    # Setup AI planner
    planner = AICommandPlanner(args.api_key, args.base_url)
    planner.set_pty_manager(manager)
    
    # Create session
    if not manager.get_session(args.session):
        manager.create_session(args.session)
    
    try:
        if args.interactive:
            # Interactive mode
            interactive = InteractivePlanner(planner)
            result = interactive.interactive_execute(args.goal, args.session)
        else:
            # Direct execution
            loop = PlanningLoop(planner)
            result = loop.execute_goal(args.goal, args.session)
        
        print(json.dumps(result, indent=2, default=str))
        
    except KeyboardInterrupt:
        print("\nExecution cancelled by user")
    finally:
        manager.close_session(args.session)


if __name__ == "__main__":
    main()