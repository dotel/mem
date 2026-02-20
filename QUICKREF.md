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

## Configuration

Example `~/.hari/config.toml`:

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

## Debugging

```bash
# Check if daemon is running
ps aux | grep harid

# Check socket exists
ls -l /tmp/hari.sock

# Memory leak check
valgrind --leak-check=full ./harid

# System call trace
strace -f ./harid
```

## Next Steps

See ROADMAP.md for detailed implementation guide.
