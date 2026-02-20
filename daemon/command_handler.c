#define _POSIX_C_SOURCE 199309L
#include <string.h>
#include <time.h>
#include "../include/hari_types.h"
#include "../include/hari_ipc.h"
#include "../include/hari_log.h"
#include "../include/hari_module.h"
#include "../include/hari_command.h"

extern hari_state_t g_state;

static uint64_t get_time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000 + (uint64_t)ts.tv_nsec / 1000000;
}

int command_dispatch(ipc_request_t* request, ipc_response_t* response) {
    response->version = IPC_PROTOCOL_VERSION;
    uint64_t now_ms = get_time_ms();
    
    if (strcmp(request->type, "ping") == 0) {
        strncpy(response->status, "ok", sizeof(response->status) - 1);
        strncpy(response->message, "Daemon is running", sizeof(response->message) - 1);
        return 0;
    }
    
    if (strcmp(request->type, "status") == 0) {
        strncpy(response->status, "ok", sizeof(response->status) - 1);
        snprintf(response->message, sizeof(response->message),
                "Uptime: %llu ms, Modules: %d", 
                (unsigned long long)g_state.uptime_ms, module_count());
        return 0;
    }
    
    if (strcmp(request->type, "pomodoro") == 0) {
        hari_event_t event = {
            .timestamp_ms = now_ms,
            .data = NULL,
            .data_size = 0
        };
        
        if (strcmp(request->payload, "start") == 0) {
            event.type = EVENT_POMODORO_START;
            module_dispatch_event(&event);
            strncpy(response->status, "ok", sizeof(response->status) - 1);
            strncpy(response->message, "Pomodoro started", sizeof(response->message) - 1);
            LOG_INFO("command", "Pomodoro start command executed");
            return 0;
        }
        else if (strcmp(request->payload, "stop") == 0 || strcmp(request->payload, "cancel") == 0) {
            event.type = EVENT_POMODORO_CANCEL;
            module_dispatch_event(&event);
            strncpy(response->status, "ok", sizeof(response->status) - 1);
            strncpy(response->message, "Pomodoro stopped", sizeof(response->message) - 1);
            LOG_INFO("command", "Pomodoro stop command executed");
            return 0;
        }
        else if (strcmp(request->payload, "pause") == 0) {
            event.type = EVENT_POMODORO_PAUSE;
            module_dispatch_event(&event);
            strncpy(response->status, "ok", sizeof(response->status) - 1);
            strncpy(response->message, "Pomodoro paused", sizeof(response->message) - 1);
            LOG_INFO("command", "Pomodoro pause command executed");
            return 0;
        }
        else {
            strncpy(response->status, "error", sizeof(response->status) - 1);
            snprintf(response->message, sizeof(response->message),
                    "Unknown pomodoro command: %s", request->payload);
            return -1;
        }
    }
    
    if (strcmp(request->type, "shutdown") == 0) {
        hari_event_t event = {
            .type = EVENT_SHUTDOWN,
            .timestamp_ms = now_ms,
            .data = NULL,
            .data_size = 0
        };
        module_dispatch_event(&event);
        strncpy(response->status, "ok", sizeof(response->status) - 1);
        strncpy(response->message, "Shutdown initiated", sizeof(response->message) - 1);
        LOG_INFO("command", "Shutdown command executed");
        return 0;
    }
    
    strncpy(response->status, "error", sizeof(response->status) - 1);
    snprintf(response->message, sizeof(response->message),
            "Unknown command: %s", request->type);
    LOG_WARN("command", "Unknown command received: %s", request->type);
    return -1;
}
