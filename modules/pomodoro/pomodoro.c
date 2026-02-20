#include <stdlib.h>
#include <string.h>
#include "../../include/hari_types.h"
#include "../../include/hari_log.h"
#include "../../include/hari_config.h"
#include "../../include/hari_module.h"
#include "pomodoro.h"

typedef enum {
    POMODORO_IDLE,
    POMODORO_WORKING,
    POMODORO_PAUSED,
    POMODORO_SHORT_BREAK,
    POMODORO_LONG_BREAK
} pomodoro_phase_t;

typedef struct {
    pomodoro_phase_t phase;
    bool active;
    uint64_t start_time;
    uint64_t pause_time;
    uint32_t duration_minutes;
    uint32_t remaining_ms;
    uint32_t session_count;
    uint32_t work_duration;
    uint32_t short_break_duration;
    uint32_t long_break_duration;
    bool auto_start_breaks;
} pomodoro_state_t;

static pomodoro_state_t g_pomodoro_state = {0};

static int pomodoro_init(void) {
    hari_config_t* config = config_get();
    
    g_pomodoro_state.phase = POMODORO_IDLE;
    g_pomodoro_state.active = false;
    g_pomodoro_state.start_time = 0;
    g_pomodoro_state.pause_time = 0;
    g_pomodoro_state.remaining_ms = 0;
    g_pomodoro_state.session_count = 0;
    
    if (config) {
        g_pomodoro_state.work_duration = config->pomodoro.duration_minutes;
        g_pomodoro_state.short_break_duration = config->pomodoro.short_break_minutes;
        g_pomodoro_state.long_break_duration = config->pomodoro.long_break_minutes;
        g_pomodoro_state.auto_start_breaks = config->pomodoro.auto_start_breaks;
    } else {
        g_pomodoro_state.work_duration = 25;
        g_pomodoro_state.short_break_duration = 5;
        g_pomodoro_state.long_break_duration = 15;
        g_pomodoro_state.auto_start_breaks = false;
    }
    
    g_pomodoro_state.duration_minutes = g_pomodoro_state.work_duration;
    
    LOG_INFO("pomodoro", "Pomodoro module initialized (work=%dm, short=%dm, long=%dm)", 
             g_pomodoro_state.work_duration, 
             g_pomodoro_state.short_break_duration,
             g_pomodoro_state.long_break_duration);
    return 0;
}

static void pomodoro_start_next_phase(uint64_t now_ms) {
    if (g_pomodoro_state.phase == POMODORO_WORKING) {
        g_pomodoro_state.session_count++;
        
        if (g_pomodoro_state.session_count % 4 == 0) {
            g_pomodoro_state.phase = POMODORO_LONG_BREAK;
            g_pomodoro_state.duration_minutes = g_pomodoro_state.long_break_duration;
            LOG_INFO("pomodoro", "Starting long break (%d minutes)", g_pomodoro_state.duration_minutes);
        } else {
            g_pomodoro_state.phase = POMODORO_SHORT_BREAK;
            g_pomodoro_state.duration_minutes = g_pomodoro_state.short_break_duration;
            LOG_INFO("pomodoro", "Starting short break (%d minutes)", g_pomodoro_state.duration_minutes);
        }
        
        if (g_pomodoro_state.auto_start_breaks) {
            g_pomodoro_state.active = true;
            g_pomodoro_state.start_time = now_ms;
        } else {
            g_pomodoro_state.active = false;
        }
    } else {
        g_pomodoro_state.phase = POMODORO_IDLE;
        g_pomodoro_state.active = false;
        LOG_INFO("pomodoro", "Break complete, ready for next work session");
    }
}

static void pomodoro_tick(uint64_t now_ms) {
    if (!g_pomodoro_state.active || g_pomodoro_state.phase == POMODORO_PAUSED) {
        return;
    }
    
    uint64_t elapsed = now_ms - g_pomodoro_state.start_time;
    uint64_t duration_ms = (uint64_t)g_pomodoro_state.duration_minutes * 60 * 1000;
    
    if (elapsed >= duration_ms) {
        const char* phase_name = (g_pomodoro_state.phase == POMODORO_WORKING) ? "Work session" : "Break";
        LOG_INFO("pomodoro", "%s complete! (session #%d)", phase_name, g_pomodoro_state.session_count);
        
        hari_event_t event = {
            .type = EVENT_POMODORO_COMPLETE,
            .timestamp_ms = now_ms,
            .data = NULL,
            .data_size = 0
        };
        module_dispatch_event(&event);
        
        pomodoro_start_next_phase(now_ms);
    } else {
        g_pomodoro_state.remaining_ms = (uint32_t)(duration_ms - elapsed);
    }
}

static void pomodoro_handle_event(hari_event_t* event) {
    switch (event->type) {
        case EVENT_POMODORO_START:
            if (g_pomodoro_state.phase == POMODORO_PAUSED) {
                LOG_INFO("pomodoro", "Resuming pomodoro session (remaining: %d ms)", 
                         g_pomodoro_state.remaining_ms);
                g_pomodoro_state.start_time = event->timestamp_ms - 
                    ((uint64_t)g_pomodoro_state.duration_minutes * 60 * 1000 - g_pomodoro_state.remaining_ms);
                g_pomodoro_state.phase = (g_pomodoro_state.session_count > 0 || 
                                         g_pomodoro_state.start_time != event->timestamp_ms) 
                                         ? POMODORO_WORKING : POMODORO_WORKING;
                g_pomodoro_state.active = true;
            } else {
                LOG_INFO("pomodoro", "Starting new pomodoro work session (%d minutes)", 
                         g_pomodoro_state.work_duration);
                g_pomodoro_state.phase = POMODORO_WORKING;
                g_pomodoro_state.active = true;
                g_pomodoro_state.start_time = event->timestamp_ms;
                g_pomodoro_state.duration_minutes = g_pomodoro_state.work_duration;
                g_pomodoro_state.remaining_ms = g_pomodoro_state.duration_minutes * 60 * 1000;
            }
            break;
            
        case EVENT_POMODORO_PAUSE:
            if (g_pomodoro_state.active && g_pomodoro_state.phase != POMODORO_PAUSED) {
                LOG_INFO("pomodoro", "Pausing pomodoro session");
                g_pomodoro_state.phase = POMODORO_PAUSED;
                g_pomodoro_state.pause_time = event->timestamp_ms;
                g_pomodoro_state.active = false;
            }
            break;
            
        case EVENT_POMODORO_CANCEL:
            LOG_INFO("pomodoro", "Cancelling pomodoro session");
            g_pomodoro_state.phase = POMODORO_IDLE;
            g_pomodoro_state.active = false;
            g_pomodoro_state.remaining_ms = 0;
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
