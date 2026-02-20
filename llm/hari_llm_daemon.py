#!/usr/bin/env python3
"""
Hari LLM Daemon
A Python daemon that handles natural language commands for Hari.
Uses Ollama for LLM inference and communicates with the C daemon via Unix socket.
"""

import socket
import json
import sys
import os
import signal
from pathlib import Path

SOCKET_PATH = "/tmp/hari_llm.sock"
HARI_DAEMON_SOCKET = "/tmp/hari.sock"

class HariLLMDaemon:
    def __init__(self):
        self.running = True
        self.socket = None
        
    def setup_signal_handlers(self):
        """Handle graceful shutdown"""
        signal.signal(signal.SIGINT, self._signal_handler)
        signal.signal(signal.SIGTERM, self._signal_handler)
        
    def _signal_handler(self, signum, frame):
        """Handle shutdown signals"""
        print(f"\n[INFO] Received signal {signum}, shutting down...")
        self.running = False
        
    def cleanup_socket(self):
        """Remove existing socket file"""
        try:
            os.unlink(SOCKET_PATH)
        except OSError:
            if os.path.exists(SOCKET_PATH):
                raise
                
    def init_socket(self):
        """Initialize Unix domain socket server"""
        self.cleanup_socket()
        
        self.socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.socket.bind(SOCKET_PATH)
        self.socket.listen(5)
        
        # Set socket to non-blocking for graceful shutdown
        self.socket.settimeout(1.0)
        
        print(f"[INFO] LLM daemon listening on {SOCKET_PATH}")
        
    def send_to_hari_daemon(self, command_type, payload=""):
        """Send command to C daemon"""
        try:
            client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            client.connect(HARI_DAEMON_SOCKET)
            
            request = {
                "version": 1,
                "type": command_type,
                "payload": payload
            }
            
            client.send(json.dumps(request).encode())
            response_data = client.recv(4096)
            client.close()
            
            return json.loads(response_data.decode())
        except Exception as e:
            print(f"[ERROR] Failed to communicate with Hari daemon: {e}")
            return {"status": "error", "message": str(e)}
            
    def parse_command(self, natural_language):
        """
        Parse natural language command using simple pattern matching.
        Later will be replaced with LLM.
        """
        text = natural_language.lower().strip()
        
        # Pomodoro start patterns
        if any(word in text for word in ["start", "begin", "commence"]):
            if any(word in text for word in ["timer", "pomodoro", "focus", "work"]):
                return {"action": "pomodoro", "command": "start"}
                
        # Pomodoro pause patterns
        if any(word in text for word in ["pause", "hold", "suspend"]):
            if any(word in text for word in ["timer", "pomodoro"]):
                return {"action": "pomodoro", "command": "pause"}
                
        # Pomodoro stop patterns
        if any(word in text for word in ["stop", "cancel", "end", "quit"]):
            if any(word in text for word in ["timer", "pomodoro"]):
                return {"action": "pomodoro", "command": "stop"}
                
        # Status
        if any(word in text for word in ["status", "how", "what"]):
            return {"action": "status", "command": ""}
            
        return None
        
    def handle_request(self, request_data):
        """Handle incoming request from CLI"""
        try:
            request = json.loads(request_data.decode())
            command_text = request.get("command", "")
            
            print(f"[INFO] Processing: '{command_text}'")
            
            # Parse natural language to structured command
            parsed = self.parse_command(command_text)
            
            if parsed is None:
                return {
                    "version": 1,
                    "status": "error",
                    "message": "Could not understand command"
                }
                
            # Execute via C daemon
            if parsed["action"] == "pomodoro":
                response = self.send_to_hari_daemon("pomodoro", parsed["command"])
            elif parsed["action"] == "status":
                response = self.send_to_hari_daemon("status")
            else:
                response = {"status": "error", "message": "Unknown action"}
                
            response["version"] = 1
            return response
            
        except json.JSONDecodeError as e:
            return {
                "version": 1,
                "status": "error",
                "message": f"Invalid JSON: {e}"
            }
        except Exception as e:
            return {
                "version": 1,
                "status": "error",
                "message": f"Error: {e}"
            }
            
    def run(self):
        """Main daemon loop"""
        self.setup_signal_handlers()
        self.init_socket()
        
        print("[INFO] Hari LLM daemon started")
        print("[INFO] Using simple pattern matching (Ollama integration next)")
        
        while self.running:
            try:
                conn, _ = self.socket.accept()
                
                # Receive request
                data = conn.recv(4096)
                if data:
                    # Process and respond
                    response = self.handle_request(data)
                    conn.send(json.dumps(response).encode())
                    
                conn.close()
                
            except socket.timeout:
                # Check if we should keep running
                continue
            except Exception as e:
                if self.running:
                    print(f"[ERROR] {e}")
                    
        self.cleanup()
        
    def cleanup(self):
        """Clean up resources"""
        print("[INFO] Cleaning up...")
        if self.socket:
            self.socket.close()
        self.cleanup_socket()
        print("[INFO] LLM daemon stopped")

def main():
    daemon = HariLLMDaemon()
    try:
        daemon.run()
    except Exception as e:
        print(f"[FATAL] {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
