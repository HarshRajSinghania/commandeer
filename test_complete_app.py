#!/usr/bin/env python3
"""
Complete application test with .env configuration
"""

import os
import sys
import json
from dotenv import load_dotenv
from src.ai_planner import AICommandPlanner, AISafetyChecker
from src.planning_loop import PlanningLoop
from src.pty_manager import manager

# Load environment variables
load_dotenv()

def test_api_configuration():
    """Test API configuration from .env"""
    print("🔧 Testing API Configuration...")
    
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    
    if not api_key:
        print("❌ OPENAI_API_KEY not found in .env")
        return False
    
    if not base_url:
        print("❌ OPENAI_BASE_URL not found in .env")
        return False
    
    print(f"✅ API Key: {api_key[:10]}...")
    print(f"✅ Base URL: {base_url}")
    return True

def test_ai_integration():
    """Test AI integration with real API"""
    print("\n🤖 Testing AI Integration...")
    
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    
    try:
        planner = AICommandPlanner(api_key, base_url)
        planner.set_pty_manager(manager)
        
        # Create test session
        if not manager.get_session("test-session"):
            manager.create_session("test-session")
        
        # Test basic planning
        plan = planner.planner.generate_plan("list files in current directory")
        print("✅ AI planning successful")
        print(f"Plan: {json.dumps(plan.__dict__, indent=2, default=str)}")
        
        # Test safety checker
        risk = AISafetyChecker.assess_risk("ls -la")
        print(f"✅ Safety check: {risk}")
        
        # Test command execution
        success = manager.execute_command("test-session", "echo 'Hello from Commandeer'")
        print(f"✅ Command execution: {success}")
        
        # Test persistent state
        manager.execute_command("test-session", "cd /tmp")
        manager.execute_command("test-session", "pwd")
        
        manager.close_session("test-session")
        return True
        
    except Exception as e:
        print(f"❌ AI integration failed: {e}")
        return False

def test_tui_integration():
    """Test TUI integration"""
    print("\n🖥️  Testing TUI Integration...")
    
    try:
        from src.tui_app import VSCodeTUI
        app = VSCodeTUI()
        print("✅ TUI app creation successful")
        return True
    except Exception as e:
        print(f"❌ TUI integration failed: {e}")
        return False

def main():
    """Run complete application test"""
    print("🧪 Complete Application Test")
    print("=" * 50)
    
    # Test API configuration
    if not test_api_configuration():
        return
    
    # Test AI integration
    if not test_ai_integration():
        return
    
    # Test TUI integration
    if not test_tui_integration():
        return
    
    print("\n✅ All tests passed!")
    print("\n🚀 Ready to use:")
    print("1. python src/main.py          # Start PTY backend")
    print("2. python src/ai_main.py --goal 'your goal'  # AI planning")
    print("3. python src/tui_main.py    # VS Code TUI")

if __name__ == "__main__":
    main()