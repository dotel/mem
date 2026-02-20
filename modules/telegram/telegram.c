#include <stdlib.h>
#include <string.h>
#include "../../include/hari_types.h"
#include "../../include/hari_log.h"
#include "../../include/hari_config.h"
#include "telegram.h"

typedef struct {
    bool enabled;
    char* token;
    char* chat_id;
} telegram_state_t;

static telegram_state_t g_telegram_state = {0};

static int telegram_init(void) {
    hari_config_t* config = config_get();
    
    if (config && config->telegram.enabled) {
        g_telegram_state.enabled = true;
        g_telegram_state.token = config->telegram.token;
        g_telegram_state.chat_id = config->telegram.chat_id;
        LOG_INFO("telegram", "Telegram module enabled");
    } else {
        g_telegram_state.enabled = false;
        LOG_INFO("telegram", "Telegram module disabled");
    }
    
    return 0;
}

static void telegram_tick(uint64_t now_ms) {
}

static void telegram_handle_event(hari_event_t* event) {
    if (!g_telegram_state.enabled) {
        return;
    }
    
    switch (event->type) {
        case EVENT_POMODORO_COMPLETE:
            LOG_INFO("telegram", "TODO: Send Pomodoro complete notification");
            break;
            
        case EVENT_USAGE_THRESHOLD:
            LOG_INFO("telegram", "TODO: Send usage threshold notification");
            break;
            
        default:
            break;
    }
}

static void telegram_shutdown(void) {
    LOG_INFO("telegram", "Telegram module shutdown");
}

static hari_module_t telegram_module = {
    .name = "telegram",
    .version = "1.0.0",
    .state = &g_telegram_state,
    .init = telegram_init,
    .tick = telegram_tick,
    .handle_event = telegram_handle_event,
    .shutdown = telegram_shutdown
};

hari_module_t* telegram_module_create(void) {
    return &telegram_module;
}
