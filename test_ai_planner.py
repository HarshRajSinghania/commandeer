#!/usr/bin/env python3
"""
Test script for AI Command Planning Layer
Tests natural language processing, safety filtering, and iterative planning
"""

import os
import json
from src.ai_planner import AICommandPlanner, AISafetyChecker
from src.planning_loop import PlanningLoop, InteractivePlanner
from src.pty_manager import manager

def test_safety_checker():
    """Test safety filtering"""
    print("🛡️  Testing Safety Checker...")
    
    test_commands = [
        ("ls -la", "safe"),
        ("rm -rf /tmp/test", "caution"),
        ("rm -rf /", "critical"),
        ("chmod 777 file.txt", "caution"),
        ("sudo apt-get update", "caution"),
        ("echo 'hello'", "safe"),
        ("dd if=/dev/zero of=/dev/sda", "critical"),
        ("find . -name '*.tmp' -delete", "caution")
    ]
    
    for command, expected in test_commands:
        risk = AISafetyChecker.assess_risk(command)
        warnings = AISafetyChecker.get_warnings(command)
        print(f"  {command} -> {risk.value} ({'✅' if risk.value == expected else '❌'})")
        if warnings:
            print(f"    Warnings: {warnings}")

def test_basic_planning():
    """Test basic planning without OpenAI (mock)"""
    print("\n🧠 Testing Basic Planning...")
    
    # Create mock planner
    planner = AICommandPlanner("mock-key")
    
    # Test with simple goal
    goal = "create a directory called 'test-dir' and list its contents"
    
    # Create session
    if not manager.get_session("test-planning"):
        manager.create_session("test-planning")
    
    try:
        # Test planning loop
        loop = PlanningLoop(planner)
        result = loop.execute_goal(goal, "test-planning")
        
        print(f"Planning Result: {json.dumps(result, indent=2, default=str)}")
        
    finally:
        manager.close_session("test-planning")

def test_integration():
    """Test integration with PTY backend"""
    print("\n🔗 Testing Integration...")
    
    # Create session
    session_id = "integration-test"
    manager.create_session(session_id)
    
    try:
        # Test direct command execution
        success = manager.execute_command(session_id, "echo 'Integration test'")
        print(f"Direct command execution: {'✅' if success else '❌'}")
        
        # Test session listing
        sessions = manager.list_sessions()
        print(f"Active sessions: {sessions}")
        
    finally:
        manager.close_session(session_id)

def test_interactive_mode():
    """Test interactive planning (manual)"""
    print("\n🎯 Interactive Mode Test")
    print("Run: python src/ai_main.py --goal 'create a test directory' --interactive")
    print("Set OPENAI_API_KEY environment variable for full testing")

def main():
    """Run all tests"""
    print("🧪 AI Command Planning Layer Tests")
    print("=" * 50)
    
    test_safety_checker()
    test_basic_planning()
    test_integration()
    test_interactive_mode()
    
    print("\n✅ All basic tests completed!")
    print("\nFor full testing:")
    print("1. Set OPENAI_API_KEY environment variable")
    print("2. Run: python src/ai_main.py --goal 'your goal here' --interactive")

if __name__ == "__main__":
    main()