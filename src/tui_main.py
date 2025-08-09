#!/usr/bin/env python3
"""
TUI Main Entry Point
Provides VS Code-inspired terminal interface
"""

import os
import sys
import argparse
from dotenv import load_dotenv
from src.tui_app import VSCodeTUI

# Load environment variables
load_dotenv()

def main():
    """Main entry point for TUI application"""
    parser = argparse.ArgumentParser(description="VS Code-inspired TUI for command execution")
    parser.add_argument("--session", help="Session ID", default="tui-session")
    parser.add_argument("--theme", help="Theme (dark/light)", default="dark")
    
    args = parser.parse_args()
    
    # Set theme environment variable
    os.environ["TEXTUAL_THEME"] = args.theme
    
    # Run the TUI
    app = VSCodeTUI()
    app.run()

if __name__ == "__main__":
    main()