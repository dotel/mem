#include <stdlib.h>
#include <string.h>
#include "../include/hari_types.h"
#include "../include/hari_module.h"
#include "../include/hari_log.h"

static hari_module_t* g_modules[HARI_MAX_MODULES];
static int g_module_count = 0;

int module_registry_init(void) {
    memset(g_modules, 0, sizeof(g_modules));
    g_module_count = 0;
    LOG_INFO("registry", "Module registry initialized");
    return 0;
}

int module_register(hari_module_t* module) {
    if (g_module_count >= HARI_MAX_MODULES) {
        LOG_ERROR("registry", "Module registry full, cannot register %s", module->name);
        return -1;
    }
    
    if (module->init && module->init() != 0) {
        LOG_ERROR("registry", "Failed to initialize module %s", module->name);
        return -1;
    }
    
    g_modules[g_module_count++] = module;
    LOG_INFO("registry", "Registered module: %s v%s", module->name, module->version);
    return 0;
}

void module_tick_all(uint64_t now_ms) {
    for (int i = 0; i < g_module_count; i++) {
        if (g_modules[i]->tick) {
            g_modules[i]->tick(now_ms);
        }
    }
}

void module_dispatch_event(hari_event_t* event) {
    for (int i = 0; i < g_module_count; i++) {
        if (g_modules[i]->handle_event) {
            g_modules[i]->handle_event(event);
        }
    }
}

void module_shutdown_all(void) {
    LOG_INFO("registry", "Shutting down all modules...");
    for (int i = 0; i < g_module_count; i++) {
        if (g_modules[i]->shutdown) {
            LOG_INFO("registry", "Shutting down module: %s", g_modules[i]->name);
            g_modules[i]->shutdown();
        }
    }
    g_module_count = 0;
}

int module_count(void) {
    return g_module_count;
}
