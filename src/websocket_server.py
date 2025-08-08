#!/usr/bin/env python3
"""
WebSocket Server for Real-time PTY Communication
Provides WebSocket interface for live command execution and output streaming
"""

import asyncio
import json
import websockets
import logging
from typing import Dict, Set
import uuid

from pty_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class WebSocketHandler:
    """Handles WebSocket connections for PTY sessions"""
    
    def __init__(self):
        self.connections: Dict[str, Set[websockets.WebSocketServerProtocol]] = {}
        self.session_outputs: Dict[str, str] = {}
    
    async def register_connection(self, session_id: str, websocket):
        """Register a new WebSocket connection for a session"""
        if session_id not in self.connections:
            self.connections[session_id] = set()
        
        self.connections[session_id].add(websocket)
        
        # Send any buffered output
        if session_id in self.session_outputs:
            await websocket.send(json.dumps({
                "type": "output",
                "data": self.session_outputs[session_id]
            }))
    
    async def unregister_connection(self, session_id: str, websocket):
        """Unregister a WebSocket connection"""
        if session_id in self.connections:
            self.connections[session_id].discard(websocket)
            if not self.connections[session_id]:
                del self.connections[session_id]
    
    async def broadcast_output(self, session_id: str, data: str):
        """Broadcast output to all WebSocket connections for a session"""
        if session_id not in self.connections:
            return
        
        # Buffer the output
        if session_id not in self.session_outputs:
            self.session_outputs[session_id] = ""
        self.session_outputs[session_id] += data
        
        # Limit buffer size
        if len(self.session_outputs[session_id]) > 10000:
            self.session_outputs[session_id] = self.session_outputs[session_id][-5000:]
        
        # Broadcast to all connected clients
        message = json.dumps({
            "type": "output",
            "data": data,
            "timestamp": time.time()
        })
        
        disconnected = set()
        for websocket in self.connections[session_id]:
            try:
                await websocket.send(message)
            except websockets.exceptions.ConnectionClosed:
                disconnected.add(websocket)
        
        # Remove disconnected clients
        for websocket in disconnected:
            self.connections[session_id].discard(websocket)
    
    async def handle_client(self, websocket, path):
        """Handle WebSocket client connection"""
        session_id = None
        
        try:
            async for message in websocket:
                try:
                    data = json.loads(message)
                    msg_type = data.get('type')
                    
                    if msg_type == 'connect':
                        session_id = data.get('session_id')
                        if not session_id:
                            await websocket.send(json.dumps({
                                "type": "error",
                                "message": "session_id required"
                            }))
                            continue
                        
                        # Create session if it doesn't exist
                        if session_id not in manager.list_sessions():
                            manager.create_session(session_id)
                        
                        # Register connection
                        await self.register_connection(session_id, websocket)
                        
                        # Set up output callback
                        session = manager.get_session(session_id)
                        if session:
                            session.add_output_callback(
                                lambda data: asyncio.create_task(
                                    self.broadcast_output(session_id, data)
                                )
                            )
                        
                        await websocket.send(json.dumps({
                            "type": "connected",
                            "session_id": session_id
                        }))
                    
                    elif msg_type == 'command' and session_id:
                        command = data.get('command')
                        if command:
                            manager.execute_command(session_id, command)
                    
                    elif msg_type == 'control' and session_id:
                        char = data.get('char')
                        if char:
                            manager.send_control(session_id, char)
                    
                    elif msg_type == 'resize' and session_id:
                        rows = data.get('rows', 24)
                        cols = data.get('cols', 80)
                        manager.resize_session(session_id, rows, cols)
                
                except json.JSONDecodeError:
                    await websocket.send(json.dumps({
                        "type": "error",
                        "message": "Invalid JSON"
                    }))
        
        except websockets.exceptions.ConnectionClosed:
            pass
        finally:
            if session_id:
                await self.unregister_connection(session_id, websocket)


class WebSocketServer:
    """WebSocket server for PTY communication"""
    
    def __init__(self, host: str = 'localhost', port: int = 8766):
        self.host = host
        self.port = port
        self.handler = WebSocketHandler()
        self.server = None
    
    async def start(self):
        """Start the WebSocket server"""
        self.server = await websockets.serve(
            self.handler.handle_client,
            self.host,
            self.port
        )
        logger.info(f"WebSocket server started on {self.host}:{self.port}")
    
    async def stop(self):
        """Stop the WebSocket server"""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            logger.info("WebSocket server stopped")


# Global server instance
websocket_server = WebSocketServer()


async def main():
    """Main entry point for WebSocket server"""
    await websocket_server.start()
    try:
        await asyncio.Future()  # Run forever
    except KeyboardInterrupt:
        await websocket_server.stop()
        manager.cleanup_all()


if __name__ == "__main__":
    asyncio.run(main())