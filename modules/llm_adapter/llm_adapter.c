#include <stdlib.h>
#include <string.h>
#include "../../include/hari_types.h"
#include "../../include/hari_log.h"
#include "../../include/hari_config.h"
#include "llm_adapter.h"

typedef struct {
    bool enabled;
    char* model_name;
    char* endpoint;
} llm_adapter_state_t;

static llm_adapter_state_t g_llm_state = {0};

static int llm_adapter_init(void) {
    hari_config_t* config = config_get();
    
    if (config && config->llm.enabled) {
        g_llm_state.enabled = true;
        g_llm_state.model_name = config->llm.model_name;
        g_llm_state.endpoint = config->llm.endpoint;
        LOG_INFO("llm_adapter", "LLM adapter enabled with model: %s", g_llm_state.model_name);
    } else {
        g_llm_state.enabled = false;
        LOG_INFO("llm_adapter", "LLM adapter disabled");
    }
    
    return 0;
}

static void llm_adapter_tick(uint64_t now_ms) {
}

static void llm_adapter_handle_event(hari_event_t* event) {
    if (!g_llm_state.enabled) {
        return;
    }
    
    switch (event->type) {
        case EVENT_LLM_COMMAND:
            LOG_INFO("llm_adapter", "TODO: Process LLM command");
            break;
            
        default:
            break;
    }
}

static void llm_adapter_shutdown(void) {
    LOG_INFO("llm_adapter", "LLM adapter module shutdown");
}

static hari_module_t llm_adapter_module = {
    .name = "llm_adapter",
    .version = "1.0.0",
    .state = &g_llm_state,
    .init = llm_adapter_init,
    .tick = llm_adapter_tick,
    .handle_event = llm_adapter_handle_event,
    .shutdown = llm_adapter_shutdown
};

hari_module_t* llm_adapter_module_create(void) {
    return &llm_adapter_module;
}
