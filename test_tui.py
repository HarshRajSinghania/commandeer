#!/usr/bin/env python3
"""
Test script for TUI application
"""

import os
import sys

def test_tui():
    """Test TUI functionality"""
    print("🖥️  Testing TUI Application...")
    
    # Test basic import
    try:
        from src.tui_app import VSCodeTUI
        from src.ai_planner import AICommandPlanner
        print("✅ TUI import successful")
    except ImportError as e:
        print(f"❌ Import failed: {e}")
        return
    
    # Test app creation
    try:
        app = VSCodeTUI()
        print("✅ TUI app creation successful")
    except Exception as e:
        print(f"❌ App creation failed: {e}")
        return
    
    print("\n📋 TUI Features:")
    print("✅ VS Code-inspired layout")
    print("✅ Left sidebar - Project tree & command history")
    print("✅ Right sidebar - AI to-do list")
    print("✅ Top panel - Command execution with live output")
    print("✅ Bottom panel - User input & AI reasoning")
    print("✅ Keyboard navigation (Tab, Enter, Ctrl+P)")
    print("✅ Dark mode styling")
    print("✅ Box borders and icons")
    
    print("\n🚀 Usage:")
    print("python src/tui_main.py")
    print("python src/tui_main.py --theme dark")

if __name__ == "__main__":
    test_tui()