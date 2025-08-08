#!/usr/bin/env python3
"""
Internal API Server for PTY Shell Backend
Provides REST API interface for command execution and session management
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs
from typing import Dict, Any
import logging

from pty_manager import manager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PTYAPIHandler(BaseHTTPRequestHandler):
    """HTTP handler for PTY API endpoints"""
    
    def _send_json_response(self, data: Dict[str, Any], status: int = 200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PUT, DELETE, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode('utf-8'))
    
    def do_OPTIONS(self):
        """Handle CORS preflight requests"""
        self._send_json_response({"status": "ok"})
    
    def do_GET(self):
        """Handle GET requests"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        if path == '/sessions':
            sessions = manager.list_sessions()
            self._send_json_response({"sessions": sessions})
            
        elif path.startswith('/sessions/'):
            session_id = path.split('/')[-1]
            session = manager.get_session(session_id)
            if session:
                self._send_json_response({
                    "session_id": session_id,
                    "is_running": session.is_running
                })
            else:
                self._send_json_response({"error": "Session not found"}, 404)
                
        else:
            self._send_json_response({"error": "Not found"}, 404)
    
    def do_POST(self):
        """Handle POST requests"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            post_data = self.rfile.read(content_length)
            data = json.loads(post_data.decode('utf-8'))
            
        except (json.JSONDecodeError, ValueError):
            self._send_json_response({"error": "Invalid JSON"}, 400)
            return
        
        if path == '/sessions':
            session_id = data.get('session_id')
            shell = data.get('shell', '/bin/bash')
            
            if not session_id:
                self._send_json_response({"error": "session_id required"}, 400)
                return
            
            success = manager.create_session(session_id, shell)
            self._send_json_response({
                "success": success,
                "session_id": session_id
            })
            
        elif path == '/execute':
            session_id = data.get('session_id')
            command = data.get('command')
            
            if not session_id or not command:
                self._send_json_response({"error": "session_id and command required"}, 400)
                return
            
            success = manager.execute_command(session_id, command)
            self._send_json_response({
                "success": success,
                "session_id": session_id,
                "command": command
            })
            
        elif path == '/control':
            session_id = data.get('session_id')
            char = data.get('char')
            
            if not session_id or not char:
                self._send_json_response({"error": "session_id and char required"}, 400)
                return
            
            success = manager.send_control(session_id, char)
            self._send_json_response({
                "success": success,
                "session_id": session_id,
                "char": char
            })
            
        elif path == '/resize':
            session_id = data.get('session_id')
            rows = data.get('rows', 24)
            cols = data.get('cols', 80)
            
            if not session_id:
                self._send_json_response({"error": "session_id required"}, 400)
                return
            
            success = manager.resize_session(session_id, rows, cols)
            self._send_json_response({
                "success": success,
                "session_id": session_id,
                "rows": rows,
                "cols": cols
            })
            
        else:
            self._send_json_response({"error": "Not found"}, 404)
    
    def do_DELETE(self):
        """Handle DELETE requests"""
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        
        if path.startswith('/sessions/'):
            session_id = path.split('/')[-1]
            success = manager.close_session(session_id)
            self._send_json_response({
                "success": success,
                "session_id": session_id
            })
        else:
            self._send_json_response({"error": "Not found"}, 404)
    
    def log_message(self, format, *args):
        """Override to reduce logging noise"""
        pass


class PTYAPIServer:
    """Main API server class"""
    
    def __init__(self, host: str = 'localhost', port: int = 8765):
        self.host = host
        self.port = port
        self.server = None
        self.thread = None
    
    def start(self):
        """Start the API server"""
        self.server = HTTPServer((self.host, self.port), PTYAPIHandler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        logger.info(f"API server started on {self.host}:{self.port}")
    
    def stop(self):
        """Stop the API server"""
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            logger.info("API server stopped")


# Global server instance
api_server = PTYAPIServer()


if __name__ == "__main__":
    api_server.start()
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        api_server.stop()
        manager.cleanup_all()