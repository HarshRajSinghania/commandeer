#!/usr/bin/env python3
"""
Automation Main Entry Point
Provides the complete AI-driven command execution system
"""

import os
import sys
import argparse
import json
import asyncio
from dotenv import load_dotenv
from src.command_flow import AICommandFlow
from src.pty_manager import manager

def main():
    """Main entry point for automation system"""
    # Load environment variables
    load_dotenv()
    
    parser = argparse.ArgumentParser(description="AI-driven command execution system")
    parser.add_argument("--api-key", help="OpenAI API key", default=os.getenv("OPENAI_API_KEY"))
    parser.add_argument("--base-url", help="OpenAI API base URL", default=os.getenv("OPENAI_BASE_URL"))
    parser.add_argument("--model", help="AI model to use", default=os.getenv("AI_MODEL"))
    parser.add_argument("--session", help="Session ID", default="automation-session")
    parser.add_argument("--goal", help="Goal to execute", required=True)
    parser.add_argument("--tui", action="store_true", help="Use TUI interface")
    
    args = parser.parse_args()
    
    if not args.api_key:
        print("Error: OpenAI API key required. Set OPENAI_API_KEY environment variable or use --api-key")
        sys.exit(1)
    
    # Setup AI flow
    flow = AICommandFlow(args.api_key, args.base_url, args.model)
    if not manager.get_session(args.session):
        manager.create_session(args.session)
    flow.set_session(args.session)
    
    if args.tui:
        # Import TUI app
        from tui_automation import AutomationTUI
        app = AutomationTUI()
        app.run()
    else:
        # Command line execution
        result = asyncio.run(flow.execute_goal(args.goal))
        print(json.dumps(result, indent=2))

if __name__ == "__main__":
    main()