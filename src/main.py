#!/usr/bin/env python3
"""
Main entry point for PTY Shell Backend
Starts both REST API and WebSocket servers
"""

import asyncio
import signal
import sys
import threading
import logging

from api_server import PTYAPIServer
from websocket_server import WebSocketServer
from pty_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PTYBackend:
    """Main backend orchestrator"""
    
    def __init__(self, api_host='localhost', api_port=8765, ws_host='localhost', ws_port=8766):
        self.api_server = PTYAPIServer(api_host, api_port)
        self.ws_server = WebSocketServer(ws_host, ws_port)
        self.running = False
    
    def start(self):
        """Start all backend services"""
        logger.info("Starting PTY Shell Backend...")
        
        # Start API server in a thread
        api_thread = threading.Thread(target=self.api_server.start, daemon=True)
        api_thread.start()
        
        # Start WebSocket server
        try:
            asyncio.run(self._start_async())
        except KeyboardInterrupt:
            self.stop()
    
    async def _start_async(self):
        """Start async services"""
        await self.ws_server.start()
        
        logger.info("PTY Shell Backend started successfully")
        logger.info(f"REST API: http://localhost:8765")
        logger.info(f"WebSocket: ws://localhost:8766")
        
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
    
    def stop(self):
        """Stop all backend services"""
        logger.info("Stopping PTY Shell Backend...")
        self.api_server.stop()
        
        async def stop_ws():
            await self.ws_server.stop()
        
        try:
            asyncio.run(stop_ws())
        except:
            pass
        
        manager.cleanup_all()
        logger.info("PTY Shell Backend stopped")


def main():
    """Main entry point"""
    backend = PTYBackend()
    
    def signal_handler(signum, frame):
        logger.info("Received shutdown signal")
        backend.stop()
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    backend.start()


if __name__ == "__main__":
    main()