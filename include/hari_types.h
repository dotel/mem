#ifndef HARI_TYPES_H
#define HARI_TYPES_H

#include <stdint.h>
#include <stdbool.h>
#include <time.h>

#define HARI_VERSION "1.0.0"
#define HARI_CONFIG_DIR ".hari"
#define HARI_SOCKET_PATH "/tmp/hari.sock"
#define HARI_MAX_MODULES 16
#define HARI_TICK_INTERVAL_MS 100

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

typedef struct {
    event_type_t type;
    uint64_t timestamp_ms;
    void* data;
    size_t data_size;
} hari_event_t;

typedef struct {
    uint64_t uptime_ms;
    uint32_t event_count;
    time_t start_time;
} hari_state_t;

typedef struct hari_module hari_module_t;

struct hari_module {
    const char* name;
    const char* version;
    void* state;
    
    int (*init)(void);
    void (*tick)(uint64_t now_ms);
    void (*handle_event)(hari_event_t* event);
    void (*shutdown)(void);
};

typedef struct {
    int (*save_state)(hari_state_t* state);
    int (*load_state)(hari_state_t* state);
    int (*append_event)(hari_event_t* event);
} storage_backend_t;

#endif
