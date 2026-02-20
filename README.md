# Hari v1 - Modular Personal Assistant Daemon

**Hari** is a local-first, modular, agentic productivity assistant daemon written in C. It focuses on time management (Pomodoro), usage monitoring, and notifications via Telegram, with optional natural language commands via local LLM.

## Architecture

Hari follows a modular, event-driven architecture:

- **Core Daemon**: Single-threaded event loop with pluggable modules
- **Module System**: Each module implements a standard interface (init, tick, handle_event, shutdown)
- **Event Bus**: Modules communicate via typed events
- **Storage Layer**: Abstracted storage with local JSON backend (remote sync planned)
- **IPC**: Unix domain socket with JSON protocol for CLI communication

## Directory Structure

```
hari/
├── daemon/          # Core daemon implementation
│   ├── main.c
│   ├── event_loop.c
│   ├── module_registry.c
│   └── storage/
├── modules/         # Pluggable modules
│   ├── pomodoro/
│   ├── usage_monitor/
│   ├── telegram/
│   └── llm_adapter/
├── ipc/             # IPC server/client implementation
├── cli/             # Command-line client
├── config/          # Configuration management
└── include/         # Shared headers
```

## Modules

### Pomodoro Module
- Start, pause, resume, cancel timers
- Auto-break handling
- State persistence
- Events: `EVENT_POMODORO_COMPLETE`, `EVENT_POMODORO_START`, `EVENT_POMODORO_CANCEL`

### Usage Monitor Module
- Track active window every N seconds
- App blacklist checking
- Usage threshold alerts
- Events: `EVENT_USAGE_THRESHOLD`

### Telegram Module
- Non-blocking notifications via Telegram Bot API
- Subscribes to: Pomodoro complete, usage threshold, daily summaries

### LLM Adapter Module
- Natural language command processing via local LLM (Ollama)
- Structured command execution (no raw text execution)
- Events: `EVENT_LLM_COMMAND`

## Building

```bash
make clean
make all
```

This produces:
- `harid` - The daemon executable
- `hari` - The CLI client

## Configuration

Configuration is stored in `~/.hari/config.toml` (TOML parsing not yet implemented, using defaults):

```toml
[pomodoro]
duration_minutes = 25
short_break_minutes = 5
long_break_minutes = 15
auto_start_breaks = false

[telegram]
enabled = false
token = "YOUR_BOT_TOKEN"
chat_id = "YOUR_CHAT_ID"

[usage_monitor]
sample_interval_seconds = 5
threshold_minutes = 120
blacklist_apps = ["Twitter", "Reddit", "Facebook"]

[llm]
enabled = false
model_name = "llama2"
endpoint = "http://localhost:11434/api/generate"
```

## Running

Start the daemon:
```bash
./harid
```

Use the CLI:
```bash
./hari ping                  # Check daemon status
./hari pomodoro start        # Start a Pomodoro session
./hari pomodoro stop         # Stop current session
./hari status                # Get daemon status
```

## State Storage

- `~/.hari/state.json` - Current state snapshot
- `~/.hari/events.log` - Event history log

## Development Status

**Phase 1 (Current)**: ✅ Skeleton Implementation
- ✅ Core daemon structure
- ✅ Module system framework
- ✅ IPC socket server/client
- ✅ Basic logging
- ✅ Configuration framework
- ✅ Storage abstraction

**Phase 2**: Module Implementation
- ⏳ Pomodoro timer logic
- ⏳ Active window detection (X11/Wayland)
- ⏳ Telegram Bot API integration (libcurl)
- ⏳ LLM adapter (Ollama integration)

**Phase 3**: Advanced Features
- ⏳ JSON parsing (config + IPC)
- ⏳ Daily summaries
- ⏳ Usage analytics
- ⏳ Proactive reminders

**Phase 4**: Future Expansion
- ⏳ Remote sync backend
- ⏳ GUI (PySide6/Tauri)
- ⏳ Additional modules

## Module Interface

To create a new module, implement the `hari_module_t` interface:

```c
typedef struct hari_module {
    const char* name;
    const char* version;
    void* state;
    
    int (*init)(void);
    void (*tick)(uint64_t now_ms);
    void (*handle_event)(hari_event_t* event);
    void (*shutdown)(void);
} hari_module_t;
```

Register your module in `daemon/main.c`:

```c
hari_module_t* my_module = my_module_create();
module_register(my_module);
```

## Dependencies

Current:
- POSIX APIs (sockets, signals, time)
- Standard C library

Future:
- `libcurl` - HTTP requests (Telegram, LLM)
- `json-c` or `cJSON` - JSON parsing
- X11/Wayland libs - Window tracking

## License

To be determined.

## Contributing

This is a personal project for Hari. Contributions welcome!

## TODO

- [ ] Implement JSON parsing for config and IPC
- [ ] Add libcurl for HTTP requests
- [ ] Implement active window detection
- [ ] Complete Telegram Bot API integration
- [ ] Add Ollama LLM integration
- [ ] Improve error handling
- [ ] Add unit tests
- [ ] Write systemd service file
- [ ] Create installation script
