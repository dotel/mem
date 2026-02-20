#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/hari_config.h"
#include "../include/hari_log.h"

static hari_config_t g_config = {0};
static bool g_config_loaded = false;

int config_init(const char* config_path) {
    g_config.pomodoro.duration_minutes = 25;
    g_config.pomodoro.short_break_minutes = 5;
    g_config.pomodoro.long_break_minutes = 15;
    g_config.pomodoro.auto_start_breaks = false;
    
    g_config.telegram.enabled = false;
    g_config.telegram.token = NULL;
    g_config.telegram.chat_id = NULL;
    
    g_config.usage_monitor.sample_interval_seconds = 5;
    g_config.usage_monitor.threshold_minutes = 120;
    g_config.usage_monitor.blacklist_apps = NULL;
    g_config.usage_monitor.blacklist_count = 0;
    
    g_config.llm.enabled = false;
    g_config.llm.model_name = strdup("llama2");
    g_config.llm.endpoint = strdup("http://localhost:11434/api/generate");
    
    g_config_loaded = true;
    LOG_INFO("config", "Configuration initialized with defaults");
    
    FILE* fp = fopen(config_path, "r");
    if (fp) {
        LOG_INFO("config", "TODO: Parse TOML config file");
        fclose(fp);
    }
    
    return 0;
}

hari_config_t* config_get(void) {
    if (!g_config_loaded) {
        return NULL;
    }
    return &g_config;
}

void config_free(void) {
    if (g_config.telegram.token) free(g_config.telegram.token);
    if (g_config.telegram.chat_id) free(g_config.telegram.chat_id);
    if (g_config.llm.model_name) free(g_config.llm.model_name);
    if (g_config.llm.endpoint) free(g_config.llm.endpoint);
    
    if (g_config.usage_monitor.blacklist_apps) {
        for (uint32_t i = 0; i < g_config.usage_monitor.blacklist_count; i++) {
            free(g_config.usage_monitor.blacklist_apps[i]);
        }
        free(g_config.usage_monitor.blacklist_apps);
    }
    
    g_config_loaded = false;
}
