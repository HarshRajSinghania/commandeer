#!/usr/bin/env python3
"""
Test script for PTY Shell Backend
Tests all core functionality including session management, command execution, and control handling
"""

import requests
import asyncio
import websockets
import json
import time
import threading

API_BASE = "http://localhost:8765"
WS_URL = "ws://localhost:8766"


def test_rest_api():
    """Test REST API functionality"""
    print("Testing REST API...")
    
    # Test session creation
    response = requests.post(f"{API_BASE}/sessions", json={
        "session_id": "test-session-1",
        "shell": "/bin/bash"
    })
    print(f"Create session: {response.json()}")
    
    # Test command execution
    response = requests.post(f"{API_BASE}/execute", json={
        "session_id": "test-session-1",
        "command": "echo 'Hello from PTY!'"
    })
    print(f"Execute command: {response.json()}")
    
    # Test session listing
    response = requests.get(f"{API_BASE}/sessions")
    print(f"List sessions: {response.json()}")
    
    # Test control character
    response = requests.post(f"{API_BASE}/control", json={
        "session_id": "test-session-1",
        "char": "C"
    })
    print(f"Send control: {response.json()}")
    
    # Test resize
    response = requests.post(f"{API_BASE}/resize", json={
        "session_id": "test-session-1",
        "rows": 30,
        "cols": 120
    })
    print(f"Resize terminal: {response.json()}")
    
    # Test session deletion
    response = requests.delete(f"{API_BASE}/sessions/test-session-1")
    print(f"Delete session: {response.json()}")


async def test_websocket():
    """Test WebSocket functionality"""
    print("\nTesting WebSocket...")
    
    async with websockets.connect(WS_URL) as websocket:
        # Connect to session
        await websocket.send(json.dumps({
            "type": "connect",
            "session_id": "test-session-2"
        }))
        
        response = await websocket.recv()
        print(f"WebSocket connect: {response}")
        
        # Send command
        await websocket.send(json.dumps({
            "type": "command",
            "command": "ls -la"
        }))
        
        # Wait for output
        try:
            output = await asyncio.wait_for(websocket.recv(), timeout=2.0)
            print(f"WebSocket output: {output[:100]}...")
        except asyncio.TimeoutError:
            print("No output received within timeout")
        
        # Test control character
        await websocket.send(json.dumps({
            "type": "control",
            "char": "C"
        }))


def run_tests():
    """Run all tests"""
    print("Starting PTY Shell Backend Tests...")
    
    # Test REST API
    try:
        test_rest_api()
    except Exception as e:
        print(f"REST API test failed: {e}")
    
    # Test WebSocket
    try:
        asyncio.run(test_websocket())
    except Exception as e:
        print(f"WebSocket test failed: {e}")
    
    print("\nTests completed!")


if __name__ == "__main__":
    run_tests()