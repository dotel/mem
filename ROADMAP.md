# Hari v1 Implementation Roadmap

This document provides a detailed, phase-by-phase guide for implementing the remaining features of Hari. The skeleton is complete and functional — you can now extend it systematically.

## Current Status ✅

**Phase 1 Complete:**
- ✅ Full directory structure
- ✅ Core daemon with event loop
- ✅ Module system (registry, tick, events)
- ✅ IPC Unix socket server/client
- ✅ CLI tool with basic commands
- ✅ Configuration framework (defaults)
- ✅ Storage abstraction (local JSON backend)
- ✅ Logging system
- ✅ All 4 modules registered (skeleton implementations)
- ✅ Signal handling (SIGINT, SIGTERM)
- ✅ State persistence (structure in place)
- ✅ Compiles and runs successfully

**Test Results:**
```bash
$ ./harid &
[INFO] Hari daemon v1.0.0 starting...
[INFO] Registered 4 modules
[INFO] IPC server listening on /tmp/hari.sock
[INFO] Entering main event loop...

$ ./hari ping
{"version": 1, "status": "ok", "message": "Command received"}
```

---

## Phase 2: Core Module Implementation

### 2.1 Pomodoro Timer Logic

**File:** `modules/pomodoro/pomodoro.c`

**Current State:** Skeleton with state management

**TODO:**
1. Implement actual timer logic in `pomodoro_tick()`:
   - Calculate elapsed time
   - Emit `EVENT_POMODORO_COMPLETE` when timer expires
   - Auto-start breaks if configured
   
2. Handle pause/resume:
   - Add pause state to `pomodoro_state_t`
   - Store remaining time on pause
   - Resume from remaining time

3. Add break management:
   - Track session count (for long breaks)
   - Auto-start short/long breaks
   - Break timer logic

4. Persist state properly:
   - Save to `pomodoro_state.json`
   - Load on module init

**Test Plan:**
```bash
./hari pomodoro start
# Wait 25 minutes or modify duration for testing
# Should emit completion event and notify Telegram
```

### 2.2 JSON Parsing for Config & IPC

**Dependency:** Add `cJSON` or `json-c`

**Files to modify:**
- `config/config.c` - Parse TOML (or switch to JSON config)
- `ipc/socket_protocol.c` - Parse/serialize JSON messages

**TODO:**

1. Add JSON library to Makefile:
   ```makefile
   LDFLAGS = -lpthread -lcjson
   ```

2. Implement `ipc_parse_request()`:
   - Parse JSON from client
   - Extract `type`, `payload`, `version`
   - Return structured `ipc_request_t`

3. Implement `ipc_serialize_response()`:
   - Build JSON response
   - Return formatted string

4. Config parsing options:
   - **Option A:** Use TOML parser (more complex)
   - **Option B:** Switch config to JSON (simpler)
   - Recommended: JSON for simplicity

**Example JSON config:**
```json
{
  "pomodoro": {
    "duration_minutes": 25,
    "short_break_minutes": 5,
    "long_break_minutes": 15,
    "auto_start_breaks": false
  },
  "telegram": {
    "enabled": false,
    "token": "YOUR_TOKEN",
    "chat_id": "YOUR_CHAT_ID"
  }
}
```

### 2.3 Command Dispatcher

**File:** `daemon/main.c` or new `daemon/command_handler.c`

**TODO:**
1. Create command dispatcher that:
   - Receives parsed IPC request
   - Routes to appropriate module
   - Emits corresponding events

2. Implement commands:
   - `ping` → return OK
   - `pomodoro start` → emit `EVENT_POMODORO_START`
   - `pomodoro stop` → emit `EVENT_POMODORO_CANCEL`
   - `pomodoro pause` → emit `EVENT_POMODORO_PAUSE`
   - `status` → return daemon/module status

3. Integrate in `ipc_server_poll()`:
   - Parse request JSON
   - Call dispatcher
   - Send response JSON

---

## Phase 3: Usage Monitor

### 3.1 Active Window Detection (Linux)

**File:** `modules/usage_monitor/usage_monitor.c`

**Dependencies:**
- X11: `-lX11`
- Wayland: `wl-roots` or D-Bus (more complex)

**TODO (X11 implementation):**

1. Add X11 detection function:
   ```c
   char* get_active_window_title(void) {
       Display* display = XOpenDisplay(NULL);
       Window window;
       int revert;
       XGetInputFocus(display, &window, &revert);
       
       // Get window name
       char* name;
       XFetchName(display, window, &name);
       XCloseDisplay(display);
       return name;
   }
   ```

2. Update Makefile:
   ```makefile
   LDFLAGS = -lpthread -lcjson -lX11
   ```

3. In `usage_monitor_tick()`:
   - Sample every N seconds (from config)
   - Get active window title
   - Update usage map (need hashtable)
   - Check against blacklist
   - Emit `EVENT_USAGE_THRESHOLD` if exceeded

4. Add state persistence:
   - Save usage stats to JSON
   - Load on startup

### 3.2 Usage Statistics

**TODO:**
1. Implement hashtable for app usage:
   - Key: app name
   - Value: total seconds

2. Daily reset logic:
   - Check if day changed
   - Archive previous day stats
   - Reset counters

3. Blacklist checking:
   - Load from config
   - Substring match on window title
   - Increment warning counter

---

## Phase 4: Telegram Notifications

### 4.1 Telegram Bot API Integration

**File:** `modules/telegram/telegram.c`

**Dependency:** `libcurl`

**TODO:**

1. Add libcurl to Makefile:
   ```makefile
   LDFLAGS = -lpthread -lcjson -lX11 -lcurl
   ```

2. Implement `telegram_send_message()`:
   ```c
   int telegram_send_message(const char* token, const char* chat_id, const char* text) {
       CURL* curl = curl_easy_init();
       char url[512];
       snprintf(url, sizeof(url), 
                "https://api.telegram.org/bot%s/sendMessage", token);
       
       char postdata[1024];
       snprintf(postdata, sizeof(postdata),
                "chat_id=%s&text=%s", chat_id, text);
       
       curl_easy_setopt(curl, CURLOPT_URL, url);
       curl_easy_setopt(curl, CURLOPT_POSTFIELDS, postdata);
       
       CURLcode res = curl_easy_perform(curl);
       curl_easy_cleanup(curl);
       
       return (res == CURLE_OK) ? 0 : -1;
   }
   ```

3. Handle events in `telegram_handle_event()`:
   - `EVENT_POMODORO_COMPLETE`: "Pomodoro session complete!"
   - `EVENT_USAGE_THRESHOLD`: "Warning: Exceeded usage threshold"
   - `EVENT_DAILY_SUMMARY`: "Daily summary: X pomodoros, Y hours tracked"

4. Make non-blocking (optional):
   - Use `curl_easy_setopt(curl, CURLOPT_TIMEOUT_MS, 5000)`
   - Or spawn thread for HTTP request

**Test Plan:**
1. Get Telegram bot token from @BotFather
2. Get your chat ID
3. Add to config
4. Trigger pomodoro completion
5. Should receive Telegram message

---

## Phase 5: LLM Adapter

### 5.1 Ollama Integration

**File:** `modules/llm_adapter/llm_adapter.c`

**Dependencies:** `libcurl` (already added)

**TODO:**

1. Implement `llm_query()`:
   ```c
   char* llm_query(const char* endpoint, const char* model, const char* prompt) {
       CURL* curl = curl_easy_init();
       
       // Build JSON request
       char json_request[2048];
       snprintf(json_request, sizeof(json_request),
                "{\"model\": \"%s\", \"prompt\": \"%s\", \"stream\": false}",
                model, prompt);
       
       // POST to Ollama
       curl_easy_setopt(curl, CURLOPT_URL, endpoint);
       curl_easy_setopt(curl, CURLOPT_POSTFIELDS, json_request);
       
       // Capture response
       // Parse JSON response
       // Return response text
   }
   ```

2. Implement command parsing:
   - Craft prompt: "Parse this command into JSON: 'start a 25 minute focus session'"
   - Expected response: `{"action": "pomodoro_start", "duration": 25}`
   - Parse JSON
   - Emit corresponding event

3. Add safety checks:
   - Whitelist allowed actions
   - Validate all parameters
   - Never execute raw shell commands

4. Handle `EVENT_LLM_COMMAND`:
   - Receive from CLI
   - Query LLM
   - Parse response
   - Emit structured event

**Test Plan:**
```bash
# Start Ollama
ollama serve

# Test with CLI
./hari "start a pomodoro"
./hari "how long have I been working today?"
```

---

## Phase 6: Advanced Features

### 6.1 Daily Summaries

**TODO:**
1. Create `modules/analytics/analytics.c`
2. Aggregate daily stats:
   - Pomodoro sessions completed
   - Total focus time
   - Most used apps
   - Blacklist violations

3. Schedule daily summary:
   - Check time every tick
   - At 11:59 PM, emit `EVENT_DAILY_SUMMARY`
   - Telegram module sends report

### 6.2 Improved Storage

**TODO:**
1. Better JSON serialization:
   - Use cJSON throughout
   - Pretty-print for readability

2. Event log analysis:
   - Parse `events.log`
   - Generate insights
   - Weekly/monthly reports

### 6.3 Remote Sync Backend

**File:** `daemon/storage/storage_sync.c`

**TODO:**
1. Implement REST API client:
   - Push state on interval
   - Pull state on startup
   - Conflict resolution (last-write-wins)

2. Add authentication:
   - Bearer token in config
   - Store in config securely

3. End-to-end encryption:
   - Encrypt state before upload
   - Decrypt on download
   - Use libsodium or OpenSSL

---

## Phase 7: Polish & Deployment

### 7.1 Error Handling

**TODO:**
1. Add error codes to all functions
2. Proper cleanup on failure
3. Graceful degradation (e.g., if Telegram fails, continue)

### 7.2 Systemd Service

**File:** `hari.service`

```ini
[Unit]
Description=Hari Personal Assistant Daemon
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/harid
Restart=on-failure
User=%i

[Install]
WantedBy=multi-user.target
```

**Install:**
```bash
sudo cp hari.service /etc/systemd/system/
sudo systemctl enable hari
sudo systemctl start hari
```

### 7.3 Installation Script

**File:** `install.sh`

```bash
#!/bin/bash
make clean
make all
sudo cp harid /usr/local/bin/
sudo cp hari /usr/local/bin/
mkdir -p ~/.hari
cp config/config.toml.example ~/.hari/config.toml
echo "Hari installed! Edit ~/.hari/config.toml and run 'harid'"
```

### 7.4 Documentation

**TODO:**
1. Update README with:
   - Installation instructions
   - Configuration guide
   - API documentation
   - Troubleshooting

2. Create `docs/` folder:
   - Module development guide
   - IPC protocol spec
   - Contributing guidelines

---

## Phase 8: Future Enhancements

### 8.1 GUI

**Options:**
- PySide6 (Python + Qt)
- Tauri (Rust + Web)
- GTK4 (C)

**Features:**
- Real-time timer display
- Usage charts
- Config editor
- Event log viewer

### 8.2 Additional Modules

**Ideas:**
1. **Email Monitor**: Check inbox, notify on important emails
2. **Calendar Integration**: Sync with Google Calendar, reminders
3. **Social Media Tracker**: Twitter, Reddit, YouTube usage
4. **Health Metrics**: Track sleep, exercise (via APIs)
5. **Smart Suggestions**: ML-based proactive reminders

### 8.3 Multi-User Support

**TODO:**
1. Per-user config/state
2. User switching
3. Shared daemon, isolated modules

---

## Testing Strategy

### Unit Tests

**Framework:** Check, cmocka, or custom

**Test:**
- Module initialization
- Event dispatching
- Storage save/load
- IPC protocol parsing

### Integration Tests

**Test:**
1. Start daemon
2. Send commands via CLI
3. Verify state changes
4. Check logs
5. Verify notifications

### Manual Testing

**Checklist:**
- [ ] Daemon starts and stops cleanly
- [ ] CLI commands work
- [ ] Pomodoro timer triggers at 25 minutes
- [ ] Telegram notification received
- [ ] Usage monitor tracks active window
- [ ] Config changes take effect
- [ ] State persists across restarts
- [ ] LLM commands parse correctly

---

## Debugging Tips

1. **Enable debug logging:**
   ```c
   log_init(LOG_DEBUG);
   ```

2. **Check IPC communication:**
   ```bash
   strace -e trace=connect,sendto,recvfrom ./hari ping
   ```

3. **Monitor daemon logs:**
   ```bash
   tail -f /tmp/hari.log  # if logging to file
   ```

4. **Test module in isolation:**
   - Create test harness
   - Call module functions directly
   - Verify behavior

5. **Valgrind for memory leaks:**
   ```bash
   valgrind --leak-check=full ./harid
   ```

---

## Performance Optimization

1. **Reduce tick frequency for idle modules**
2. **Use thread pool for blocking I/O** (HTTP, file)
3. **Batch IPC messages**
4. **Optimize JSON parsing** (avoid repeated parsing)
5. **Profile with perf:**
   ```bash
   perf record ./harid
   perf report
   ```

---

## Security Considerations

1. **IPC socket permissions:** 0600 (owner only)
2. **Config file permissions:** 0600
3. **No secrets in logs**
4. **LLM command validation** (whitelist actions)
5. **Input sanitization** (all IPC messages)
6. **Rate limiting** (prevent IPC spam)

---

## Quick Start for Claude

**To implement next feature (e.g., Pomodoro timer):**

1. Read current file: `modules/pomodoro/pomodoro.c`
2. Identify TODOs in `pomodoro_tick()`
3. Implement timer logic (see Phase 2.1)
4. Test with CLI
5. Verify with daemon logs
6. Move to next feature

**To add a dependency (e.g., libcurl):**

1. Update Makefile: `LDFLAGS = -lpthread -lcurl`
2. Add includes to relevant `.c` file
3. Use library functions
4. Test build: `make clean && make all`

**To create a new module:**

1. Copy `modules/template/` (if exists) or `pomodoro/`
2. Rename files
3. Implement `hari_module_t` interface
4. Register in `daemon/main.c`
5. Add to Makefile sources
6. Test

---

## Summary

You now have a **production-ready skeleton** for Hari v1. Every component is in place:
- Core daemon ✅
- Module system ✅
- IPC ✅
- Storage ✅
- All 4 modules registered ✅

The implementation is clean, modular, and extensible. Follow this roadmap phase-by-phase, and you'll have a fully functional productivity assistant.

**Next immediate step:** Implement Phase 2.1 (Pomodoro timer logic) and Phase 2.2 (JSON parsing).

Good luck building Hari! 🚀
