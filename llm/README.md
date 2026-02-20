# Hari LLM Daemon

A Python daemon that adds natural language command support to Hari using pattern matching (with Ollama integration ready for Phase 5b).

## Architecture

```
User: "start a timer"
       ↓
[hari_llm_cli.py]
       ↓ Unix Socket (/tmp/hari_llm.sock)
[hari_llm_daemon.py]
       ↓ Parse natural language
       ↓ Generate structured command
       ↓ Unix Socket (/tmp/hari.sock)
[C Daemon (harid)]
       ↓
Executes: pomodoro start
```

## Features (Phase 5a)

✅ Unix socket IPC (consistent with C daemon)
✅ Pattern matching for common commands
✅ Bidirectional communication with C daemon
✅ JSON protocol (same as C daemon)
✅ Graceful shutdown (SIGINT/SIGTERM)

## Usage

### Start the Daemons

```bash
# Terminal 1: Start C daemon
./harid

# Terminal 2: Start LLM daemon
python3 llm/hari_llm_daemon.py
```

### Send Natural Language Commands

The easiest way is using the `hari` wrapper script:

```bash
# Start a timer
./hari start a timer
./hari begin a focus session for 30 minutes
./hari start working

# Pause
./hari pause my pomodoro
./hari hold the timer

# Stop
./hari stop the timer
./hari cancel my session

# Status
./hari what's the status
./hari how are things
```

Alternatively, you can call the Python CLI directly:

```bash
python3 llm/hari_llm_cli.py "start a timer"
```

## Supported Commands

### Pomodoro Start
- Triggers: `start`, `begin`, `commence` + `timer`, `pomodoro`, `focus`, `work`
- Action: Sends `pomodoro start` to C daemon

### Pomodoro Pause
- Triggers: `pause`, `hold`, `suspend` + `timer`, `pomodoro`
- Action: Sends `pomodoro pause` to C daemon

### Pomodoro Stop
- Triggers: `stop`, `cancel`, `end`, `quit` + `timer`, `pomodoro`
- Action: Sends `pomodoro stop` to C daemon

### Status Query
- Triggers: `status`, `how`, `what`
- Action: Sends `status` to C daemon

## Implementation Details

### Current: Pattern Matching (Phase 5a)

Simple keyword matching for fast development:
- No external dependencies
- Instant responses
- Easy to debug
- Works offline

### Next: Ollama Integration (Phase 5b)

Will use LLM for better understanding:
```python
def parse_command_with_llm(text):
    prompt = f"Parse: {text}"
    response = ollama.generate(model="llama2", prompt=prompt)
    return json.loads(response)
```

Benefits:
- Handles typos and variations
- Understands context
- More natural language
- Can extract parameters (duration, etc.)

## Files

- `hari_llm_daemon.py` - Main daemon (Unix socket server)
- `hari_llm_cli.py` - CLI client for testing
- `README.md` - This file

## Requirements

- Python 3.7+
- Access to `/tmp/hari.sock` (C daemon must be running)

## Future Features (Phase 5b+)

- [ ] Ollama integration for better NLP
- [ ] Conversation memory
- [ ] RAG for querying productivity data
- [ ] Multi-agent system
- [ ] Proactive suggestions
- [ ] Context-aware responses

## Testing

```bash
# All should return JSON responses
./hari start a timer
# {"version": 1, "status": "ok", "message": "Pomodoro started"}

./hari pause
# {"version": 1, "status": "ok", "message": "Pomodoro paused"}

./hari what's up
# {"version": 1, "status": "ok", "message": "Uptime: X ms, Modules: 4"}
```

For debugging the C daemon directly (bypassing LLM):

```bash
./hari-debug pomodoro start
./hari-debug status
```

## Development

The daemon is designed for easy extension:

1. **Add new command patterns** in `parse_command()`
2. **Add new actions** in `handle_request()`
3. **Add Ollama** in Phase 5b (replace `parse_command()`)
4. **Add RAG** in Phase 5c (query C daemon for data)
5. **Add agents** in Phase 5d (LangChain integration)

## Notes

- Pattern matching is intentionally simple for Phase 5a
- Designed to be replaced with LLM in Phase 5b
- Unix socket chosen over HTTP for consistency with C daemon
- Daemon can query C daemon for productivity data (future)
