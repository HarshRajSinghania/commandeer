#!/usr/bin/env python3
"""
Persistent PTY Session Manager
Handles persistent terminal sessions with state management
"""

import os
import pty
import subprocess
import threading
import select
import termios
import fcntl
import struct
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class PTYSession:
    """Manages a single persistent PTY session"""
    
    def __init__(self, session_id: str, shell: str = "/bin/bash"):
        self.session_id = session_id
        self.shell = shell
        self.master_fd = None
        self.slave_fd = None
        self.process = None
        self.is_running = False
        self.output_callbacks = []
        self.exit_callbacks = []
        self._output_thread = None
        
    def start(self) -> bool:
        """Start the PTY session"""
        try:
            # Create PTY
            self.master_fd, self.slave_fd = pty.openpty()
            
            # Start shell process
            self.process = subprocess.Popen(
                [self.shell],
                stdin=self.slave_fd,
                stdout=self.slave_fd,
                stderr=self.slave_fd,
                preexec_fn=os.setsid
            )
            
            # Close slave fd in parent
            os.close(self.slave_fd)
            self.slave_fd = None
            
            self.is_running = True
            
            # Start output reading thread
            self._output_thread = threading.Thread(
                target=self._read_output,
                daemon=True
            )
            self._output_thread.start()
            
            logger.info(f"PTY session {self.session_id} started")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start PTY session: {e}")
            self.cleanup()
            return False
    
    def _read_output(self):
        """Read output from PTY and notify callbacks"""
        while self.is_running and self.master_fd is not None:
            try:
                # Check if data is available
                ready, _, _ = select.select([self.master_fd], [], [], 0.1)
                
                if ready:
                    data = os.read(self.master_fd, 1024)
                    if data:
                        decoded_data = data.decode('utf-8', errors='replace')
                        for callback in self.output_callbacks:
                            callback(decoded_data)
                    else:
                        # EOF reached
                        break
                        
            except OSError:
                # PTY closed
                break
            except Exception as e:
                logger.error(f"Error reading output: {e}")
                break
        
        self.is_running = False
        for callback in self.exit_callbacks:
            callback()
    
    def execute_command(self, command: str) -> bool:
        """Execute a command in the PTY session"""
        if not self.is_running or self.master_fd is None:
            return False
        
        try:
            # Ensure command ends with newline
            if not command.endswith('\n'):
                command += '\n'
            
            os.write(self.master_fd, command.encode('utf-8'))
            return True
            
        except Exception as e:
            logger.error(f"Failed to execute command: {e}")
            return False
    
    def send_control_character(self, char: str) -> bool:
        """Send control character (e.g., Ctrl+C)"""
        if not self.is_running or self.master_fd is None:
            return False
        
        try:
            # Convert Ctrl+C to actual control character
            if char.upper() == 'C':
                control_char = b'\x03'  # ETX (End of Text) - Ctrl+C
            elif char.upper() == 'D':
                control_char = b'\x04'  # EOT (End of Transmission) - Ctrl+D
            elif char.upper() == 'Z':
                control_char = b'\x1a'  # SUB (Substitute) - Ctrl+Z
            else:
                return False
            
            os.write(self.master_fd, control_char)
            return True
            
        except Exception as e:
            logger.error(f"Failed to send control character: {e}")
            return False
    
    def resize(self, rows: int, cols: int) -> bool:
        """Resize the PTY terminal"""
        if not self.is_running or self.master_fd is None:
            return False
        
        try:
            # Use TIOCSWINSZ to set window size
            winsize = struct.pack('HHHH', rows, cols, 0, 0)
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
            return True
            
        except Exception as e:
            logger.error(f"Failed to resize PTY: {e}")
            return False
    
    def add_output_callback(self, callback):
        """Add callback for output data"""
        self.output_callbacks.append(callback)
    
    def add_exit_callback(self, callback):
        """Add callback for session exit"""
        self.exit_callbacks.append(callback)
    
    def cleanup(self):
        """Clean up resources"""
        self.is_running = False
        
        if self.master_fd is not None:
            try:
                os.close(self.master_fd)
            except:
                pass
            self.master_fd = None
        
        if self.slave_fd is not None:
            try:
                os.close(self.slave_fd)
            except:
                pass
            self.slave_fd = None
        
        if self.process and self.process.poll() is None:
            try:
                self.process.terminate()
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        
        logger.info(f"PTY session {self.session_id} cleaned up")


class PTYManager:
    """Manages multiple PTY sessions"""
    
    def __init__(self):
        self.sessions = {}
        self.lock = threading.Lock()
    
    def create_session(self, session_id: str, shell: str = "/bin/bash") -> bool:
        """Create a new PTY session"""
        with self.lock:
            if session_id in self.sessions:
                return False
            
            session = PTYSession(session_id, shell)
            if session.start():
                self.sessions[session_id] = session
                return True
            return False
    
    def get_session(self, session_id: str):
        """Get a PTY session by ID"""
        with self.lock:
            return self.sessions.get(session_id)
    
    def execute_command(self, session_id: str, command: str) -> bool:
        """Execute command in specified session"""
        session = self.get_session(session_id)
        if session:
            return session.execute_command(command)
        return False
    
    def send_control(self, session_id: str, char: str) -> bool:
        """Send control character to session"""
        session = self.get_session(session_id)
        if session:
            return session.send_control_character(char)
        return False
    
    def resize_session(self, session_id: str, rows: int, cols: int) -> bool:
        """Resize a session's terminal"""
        session = self.get_session(session_id)
        if session:
            return session.resize(rows, cols)
        return False
    
    def close_session(self, session_id: str) -> bool:
        """Close a PTY session"""
        with self.lock:
            session = self.sessions.pop(session_id, None)
            if session:
                session.cleanup()
                return True
            return False
    
    def list_sessions(self) -> list:
        """List all active session IDs"""
        return list(self.sessions.keys())
    
    def cleanup_all(self):
        """Clean up all sessions"""
        with self.lock:
            for session in self.sessions.values():
                session.cleanup()
            self.sessions.clear()


# Global manager instance
manager = PTYManager()