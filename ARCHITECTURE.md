# Hari Architecture Documentation

## Overview

Hari is designed as a modular, event-driven daemon with a clear separation of concerns. The architecture prioritizes extensibility, maintainability, and local-first operation.

## Core Components

### 1. Event Loop (`daemon/main.c`)

The heart of Hari is a single-threaded event loop that:
- Accepts IPC commands from the CLI
- Ticks all registered modules at regular intervals (100ms)
- Dispatches events to interested modules
- Periodically flushes state to disk
- Handles shutdown signals gracefully

```
┌─────────────────────────────────────┐
│         Main Event Loop             │
│  ┌───────────────────────────────┐  │
│  │ 1. Handle IPC requests        │  │
│  │ 2. Tick all modules           │  │
│  │ 3. Dispatch queued events     │  │
│  │ 4. Flush state (every 60s)    │  │
│  │ 5. Sleep (100ms)              │  │
│  └───────────────────────────────┘  │
└─────────────────────────────────────┘
```

### 2. Module System (`daemon/module_registry.c`)

Modules are the building blocks of Hari's functionality. Each module:
- Implements a standard interface (`hari_module_t`)
- Maintains its own internal state
- Can subscribe to and emit events
- Is completely independent of other modules

**Module Interface:**
```c
typedef struct hari_module {
    const char* name;
    const char* version;
    void* state;
    
    int (*init)(void);                         // Initialize module
    void (*tick)(uint64_t now_ms);            // Called every loop iteration
    void (*handle_event)(hari_event_t* evt);  // Handle events
    void (*shutdown)(void);                    // Cleanup
} hari_module_t;
```

### 3. Event Bus (`daemon/event_loop.c`)

The event bus enables loose coupling between modules:
- Modules emit events (e.g., `EVENT_POMODORO_COMPLETE`)
- Other modules subscribe by implementing `handle_event()`
- Events are queued and dispatched during the event loop

**Event Flow:**
```
Pomodoro Module → EVENT_POMODORO_COMPLETE → Event Queue
                                           ↓
                              ┌─────────────────────┐
                              │ Event Dispatcher    │
                              └─────────────────────┘
                                ↓              ↓
                      Telegram Module   Storage Module
                      (sends notification) (logs event)
```

### 4. Storage Layer (`daemon/storage/`)

Abstracted storage with pluggable backends:

**Current Implementation:**
- `storage_local.c`: JSON files in `~/.hari/`
  - `state.json`: Snapshot of current state
  - `events.log`: Append-only event log

**Future Implementation:**
- `storage_sync.c`: Push/pull to remote server

**Storage Interface:**
```c
typedef struct {
    int (*save_state)(hari_state_t* state);
    int (*load_state)(hari_state_t* state);
    int (*append_event)(hari_event_t* event);
} storage_backend_t;
```

### 5. IPC System (`ipc/`)

Unix domain socket with JSON protocol:

**Protocol:**
```json
// Request
{
  "version": 1,
  "type": "command",
  "payload": "start pomodoro"
}

// Response
{
  "version": 1,
  "status": "ok",
  "message": "Pomodoro started"
}
```

**Flow:**
```
CLI Client → Unix Socket → IPC Server → Command Handler → Module Event
           (hari)      (/tmp/hari.sock)   (daemon)
```

## Module Architecture

### Pomodoro Module
```
State:
  - active: bool
  - start_time: timestamp
  - duration_minutes: uint32
  - remaining_ms: uint64

Events Emitted:
  - EVENT_POMODORO_COMPLETE

Events Handled:
  - EVENT_POMODORO_START
  - EVENT_POMODORO_CANCEL

Tick Behavior:
  - Check if timer expired
  - Emit completion event
  - Update remaining time
```

### Usage Monitor Module
```
State:
  - last_sample_time: timestamp
  - app_usage_map: HashMap<app, minutes>
  - threshold_warned: bool

Events Emitted:
  - EVENT_USAGE_THRESHOLD

Events Handled:
  - None

Tick Behavior:
  - Sample active window every 5s
  - Update usage counters
  - Check against blacklist
  - Emit threshold event if exceeded
```

### Telegram Module
```
State:
  - enabled: bool
  - token: string
  - chat_id: string

Events Emitted:
  - None

Events Handled:
  - EVENT_POMODORO_COMPLETE
  - EVENT_USAGE_THRESHOLD
  - EVENT_DAILY_SUMMARY

Tick Behavior:
  - None (purely reactive)

Implementation:
  - Uses libcurl for HTTP requests
  - Non-blocking (async or thread pool)
```

### LLM Adapter Module
```
State:
  - enabled: bool
  - model_name: string
  - endpoint: string

Events Emitted:
  - EVENT_POMODORO_START (parsed from LLM response)
  - Other structured events

Events Handled:
  - EVENT_LLM_COMMAND (from CLI)

Tick Behavior:
  - None

Implementation:
  - Sends prompt to Ollama
  - Parses JSON response
  - Emits structured events (NOT raw commands)
```

## Data Flow Examples

### Example 1: Starting a Pomodoro via CLI
```
1. User runs: `hari pomodoro start`
2. CLI serializes JSON request
3. CLI connects to /tmp/hari.sock
4. IPC server receives request
5. Server parses JSON, identifies "pomodoro start"
6. Server emits EVENT_POMODORO_START
7. Pomodoro module handles event
8. Pomodoro module sets state: active=true, start_time=now
9. Server sends JSON response to CLI
10. CLI prints "Pomodoro started"
```

### Example 2: Pomodoro Completion
```
1. Pomodoro module tick() detects timer expired
2. Module emits EVENT_POMODORO_COMPLETE
3. Event dispatcher broadcasts to all modules
4. Telegram module receives event
5. Telegram module makes async HTTP POST to Telegram API
6. Storage module receives event
7. Storage module appends to events.log
8. Pomodoro module resets state
```

### Example 3: Natural Language Command
```
1. User runs: `hari "start a 25 minute focus session"`
2. CLI sends EVENT_LLM_COMMAND with text payload
3. LLM Adapter module receives event
4. Module sends prompt to Ollama: "Parse this command: ..."
5. Ollama returns JSON: {"action": "pomodoro_start", "duration": 25}
6. Module emits EVENT_POMODORO_START with parsed data
7. Pomodoro module handles event
8. Response flows back to CLI
```

## Extension Points

### Adding a New Module

1. Create `modules/mymodule/mymodule.c`
2. Implement `hari_module_t` interface
3. Define module-specific state struct
4. Register in `daemon/main.c`:
   ```c
   hari_module_t* my_module = my_module_create();
   module_register(my_module);
   ```

### Adding a New Event Type

1. Add to `event_type_t` enum in `include/hari_types.h`
2. Document in this file
3. Emit from producer module
4. Handle in consumer module(s)

### Adding a Storage Backend

1. Create `daemon/storage/storage_custom.c`
2. Implement `storage_backend_t` interface
3. Expose via `storage_get_custom_backend()`
4. Select in `storage_init()`

## Security Considerations

### LLM Safety
- Never execute raw LLM output as shell commands
- Always parse LLM responses into structured events
- Validate all parameters before execution
- Whitelist allowed actions

### IPC Security
- Unix socket with file permissions (0600)
- Protocol versioning for compatibility
- Input validation on all IPC messages
- Rate limiting (future)

### Data Privacy
- All data stored locally by default
- Encrypted sync backend (future)
- No telemetry or analytics

## Performance Considerations

### Single-Threaded Design
- Simplifies state management (no locks)
- Sufficient for typical usage patterns
- Future: Optional thread pool for heavy tasks (HTTP, LLM)

### Tick Interval
- 100ms provides good responsiveness
- Modules implement their own sampling logic
- Future: Variable tick rates per module

### Memory Management
- Static allocation where possible
- Careful use of malloc/free
- Event queue has fixed size (prevents unbounded growth)

## Future Architecture Enhancements

### Multi-Threading
- Thread pool for blocking operations (HTTP, LLM)
- Message passing via lock-free queues
- Main loop remains single-threaded

### Remote Sync
- Push state changes to server on interval
- Pull updates on startup
- Conflict resolution (last-write-wins)
- End-to-end encryption

### GUI Integration
- GUI as separate process
- Communicates via IPC (same as CLI)
- Real-time updates via event subscription
- Cross-platform (PySide6 or Tauri)

### Advanced Modules
- Social media monitor (API scraping)
- Email checker (IMAP)
- Calendar integration
- Health metrics (activity, sleep)
- Proactive suggestions (ML model)
