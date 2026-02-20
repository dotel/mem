# Hari Quick Reference

## Build & Run

```bash
# Build
make clean && make all

# Run daemon
./harid

# Run daemon in background
./harid &

# Stop daemon
killall harid

# Run with debug logging (modify daemon/main.c)
log_init(LOG_DEBUG);
```

## CLI Commands

```bash
# Check if daemon is running
./hari ping

# Start Pomodoro session
./hari pomodoro start

# Stop Pomodoro session
./hari pomodoro stop

# Get status
./hari status
```

## File Locations

```
~/.hari/                      # Config directory
~/.hari/config.toml           # Configuration file
~/.hari/state.json            # Current state snapshot
~/.hari/events.log            # Event history
/tmp/hari.sock                # IPC Unix socket
```

## Project Structure

```
hari/
├── daemon/              # Core daemon
│   ├── main.c          # Entry point, event loop
│   ├── module_registry.c
│   ├── event_loop.c
│   ├── hari_log.c
│   └── storage/        # Storage backends
│
├── modules/            # Feature modules
│   ├── pomodoro/
│   ├── usage_monitor/
│   ├── telegram/
│   └── llm_adapter/
│
├── ipc/                # IPC system
│   ├── socket_server.c
│   └── socket_protocol.c
│
├── cli/                # CLI client
│   ├── main.c
│   └── socket_client.c
│
├── config/             # Config management
│   └── config.c
│
└── include/            # Headers
    ├── hari_types.h    # Core types
    ├── hari_module.h   # Module interface
    ├── hari_ipc.h      # IPC protocol
    ├── hari_storage.h  # Storage interface
    ├── hari_config.h   # Config interface
    └── hari_log.h      # Logging
```

## Module Interface

Every module implements:

```c
typedef struct {
    const char* name;
    const char* version;
    void* state;
    
    int (*init)(void);                    // Called once at startup
    void (*tick)(uint64_t now_ms);        // Called every 100ms
    void (*handle_event)(hari_event_t*);  // Handle events
    void (*shutdown)(void);               // Called on shutdown
} hari_module_t;
```

## Event System

```c
// Event types
typedef enum {
    EVENT_POMODORO_COMPLETE,
    EVENT_POMODORO_START,
    EVENT_POMODORO_PAUSE,
    EVENT_POMODORO_CANCEL,
    EVENT_USAGE_THRESHOLD,
    EVENT_LLM_COMMAND,
    EVENT_DAILY_SUMMARY,
    EVENT_SHUTDOWN
} event_type_t;

// Emit event (in module)
hari_event_t event = {
    .type = EVENT_POMODORO_COMPLETE,
    .timestamp_ms = now_ms,
    .data = NULL,
    .data_size = 0
};
module_dispatch_event(&event);
```

## Adding a New Module

1. Create `modules/mymodule/mymodule.c` and `.h`
2. Implement module interface
3. Add to Makefile DAEMON_SOURCES
4. Register in `daemon/main.c`:
   ```c
   extern hari_module_t* mymodule_create(void);
   
   hari_module_t* mymodule = mymodule_create();
   if (mymodule) module_register(mymodule);
   ```

## IPC Protocol

### Request Format
```json
{
  "version": 1,
  "type": "command",
  "payload": "start pomodoro"
}
```

### Response Format
```json
{
  "version": 1,
  "status": "ok",
  "message": "Command received"
}
```

## Configuration

Default config locations: `~/.hari/config.toml`

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
blacklist_apps = ["Twitter", "Reddit"]

[llm]
enabled = false
model_name = "llama2"
endpoint = "http://localhost:11434/api/generate"
```

## Logging

```c
LOG_DEBUG("module", "Debug message");
LOG_INFO("module", "Info message");
LOG_WARN("module", "Warning message");
LOG_ERROR("module", "Error message");
```

## Debugging

```bash
# Check if daemon is running
ps aux | grep harid

# Check socket exists
ls -l /tmp/hari.sock

# Test socket manually
echo '{"version":1,"type":"ping"}' | nc -U /tmp/hari.sock

# Monitor daemon output (if running in foreground)
./harid

# Memory leak check
valgrind --leak-check=full ./harid

# System call trace
strace -f ./harid
```

## Dependencies

Current (minimal):
- Standard C library
- POSIX APIs (sockets, signals, time)

Future:
- `libcurl` - HTTP requests (Telegram, LLM)
- `cJSON` or `json-c` - JSON parsing
- `libX11` - Window tracking (Linux X11)

## Common Issues

**Problem:** "Cannot connect to daemon"
- Check if daemon is running: `ps aux | grep harid`
- Check socket exists: `ls /tmp/hari.sock`
- Try starting daemon: `./harid`

**Problem:** "Compilation errors"
- Run `make clean` first
- Check all includes are correct
- Verify gcc version: `gcc --version`

**Problem:** "Daemon crashes immediately"
- Run in foreground: `./harid`
- Check error messages
- Verify `~/.hari` directory exists and is writable

## Performance Notes

- Tick interval: 100ms (configurable in `hari_types.h`)
- State saved every 60 seconds
- IPC timeout: None (blocking)
- Max modules: 16 (configurable in `hari_types.h`)

## Next Steps

1. Implement Pomodoro timer logic (Phase 2.1)
2. Add JSON parsing (Phase 2.2)
3. Implement command dispatcher (Phase 2.3)
4. Add X11 window tracking (Phase 3.1)
5. Integrate Telegram (Phase 4.1)
6. Add LLM adapter (Phase 5.1)

See ROADMAP.md for detailed implementation guide.
