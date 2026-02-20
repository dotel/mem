#include <stdlib.h>
#include <string.h>
#include "../../include/hari_types.h"
#include "../../include/hari_log.h"
#include "../../include/hari_config.h"
#include "pomodoro.h"

typedef struct {
    bool active;
    uint64_t start_time;
    uint32_t duration_minutes;
    uint32_t remaining_ms;
} pomodoro_state_t;

static pomodoro_state_t g_pomodoro_state = {0};

static int pomodoro_init(void) {
    g_pomodoro_state.active = false;
    g_pomodoro_state.start_time = 0;
    g_pomodoro_state.duration_minutes = 25;
    g_pomodoro_state.remaining_ms = 0;
    
    LOG_INFO("pomodoro", "Pomodoro module initialized");
    return 0;
}

static void pomodoro_tick(uint64_t now_ms) {
    if (!g_pomodoro_state.active) {
        return;
    }
    
    uint64_t elapsed = now_ms - g_pomodoro_state.start_time;
    uint64_t duration_ms = g_pomodoro_state.duration_minutes * 60 * 1000;
    
    if (elapsed >= duration_ms) {
        LOG_INFO("pomodoro", "Pomodoro session complete!");
        g_pomodoro_state.active = false;
        
        hari_event_t event = {
            .type = EVENT_POMODORO_COMPLETE,
            .timestamp_ms = now_ms,
            .data = NULL,
            .data_size = 0
        };
    }
}

static void pomodoro_handle_event(hari_event_t* event) {
    switch (event->type) {
        case EVENT_POMODORO_START:
            LOG_INFO("pomodoro", "Starting pomodoro session");
            g_pomodoro_state.active = true;
            g_pomodoro_state.start_time = event->timestamp_ms;
            break;
            
        case EVENT_POMODORO_CANCEL:
            LOG_INFO("pomodoro", "Cancelling pomodoro session");
            g_pomodoro_state.active = false;
            break;
            
        default:
            break;
    }
}

static void pomodoro_shutdown(void) {
    LOG_INFO("pomodoro", "Pomodoro module shutdown");
}

static hari_module_t pomodoro_module = {
    .name = "pomodoro",
    .version = "1.0.0",
    .state = &g_pomodoro_state,
    .init = pomodoro_init,
    .tick = pomodoro_tick,
    .handle_event = pomodoro_handle_event,
    .shutdown = pomodoro_shutdown
};

hari_module_t* pomodoro_module_create(void) {
    return &pomodoro_module;
}
