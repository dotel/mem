#!/usr/bin/env python3
"""
Hari LLM CLI Client
Sends natural language commands to the LLM daemon
"""

import socket
import json
import sys

SOCKET_PATH = "/tmp/hari_llm.sock"

def send_command(command_text):
    """Send natural language command to LLM daemon"""
    try:
        client = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        client.connect(SOCKET_PATH)
        
        request = {
            "command": command_text
        }
        
        client.send(json.dumps(request).encode())
        response_data = client.recv(4096)
        client.close()
        
        response = json.loads(response_data.decode())
        return response
        
    except FileNotFoundError:
        return {
            "status": "error",
            "message": "LLM daemon not running. Start with: ./llm/hari_llm_daemon.py"
        }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to communicate: {e}"
        }

def main():
    if len(sys.argv) < 2:
        print("Usage: hari-llm <natural language command>")
        print("Examples:")
        print('  hari-llm "start a timer"')
        print('  hari-llm "pause my pomodoro"')
        print('  hari-llm "stop the timer"')
        sys.exit(1)
        
    command = " ".join(sys.argv[1:])
    response = send_command(command)
    
    print(json.dumps(response, indent=2))
    
    if response.get("status") == "error":
        sys.exit(1)

if __name__ == "__main__":
    main()
