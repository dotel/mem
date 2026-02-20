#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <json-c/json.h>
#include "../include/hari_config.h"
#include "../include/hari_log.h"

static hari_config_t g_config = {0};
static bool g_config_loaded = false;

static int config_load_json(const char* config_path) {
    FILE* fp = fopen(config_path, "r");
    if (!fp) {
        return -1;
    }
    
    fseek(fp, 0, SEEK_END);
    long file_size = ftell(fp);
    fseek(fp, 0, SEEK_SET);
    
    char* json_str = malloc(file_size + 1);
    if (!json_str) {
        fclose(fp);
        return -1;
    }
    
    fread(json_str, 1, file_size, fp);
    json_str[file_size] = '\0';
    fclose(fp);
    
    struct json_object* root = json_tokener_parse(json_str);
    free(json_str);
    
    if (!root) {
        LOG_ERROR("config", "Failed to parse config JSON");
        return -1;
    }
    
    struct json_object* pomodoro = NULL;
    if (json_object_object_get_ex(root, "pomodoro", &pomodoro)) {
        struct json_object* temp = NULL;
        
        if (json_object_object_get_ex(pomodoro, "duration_minutes", &temp))
            g_config.pomodoro.duration_minutes = json_object_get_int(temp);
        
        if (json_object_object_get_ex(pomodoro, "short_break_minutes", &temp))
            g_config.pomodoro.short_break_minutes = json_object_get_int(temp);
        
        if (json_object_object_get_ex(pomodoro, "long_break_minutes", &temp))
            g_config.pomodoro.long_break_minutes = json_object_get_int(temp);
        
        if (json_object_object_get_ex(pomodoro, "auto_start_breaks", &temp))
            g_config.pomodoro.auto_start_breaks = json_object_get_boolean(temp);
    }
    
    struct json_object* telegram = NULL;
    if (json_object_object_get_ex(root, "telegram", &telegram)) {
        struct json_object* temp = NULL;
        
        if (json_object_object_get_ex(telegram, "enabled", &temp))
            g_config.telegram.enabled = json_object_get_boolean(temp);
        
        if (json_object_object_get_ex(telegram, "token", &temp))
            g_config.telegram.token = strdup(json_object_get_string(temp));
        
        if (json_object_object_get_ex(telegram, "chat_id", &temp))
            g_config.telegram.chat_id = strdup(json_object_get_string(temp));
    }
    
    struct json_object* usage = NULL;
    if (json_object_object_get_ex(root, "usage_monitor", &usage)) {
        struct json_object* temp = NULL;
        
        if (json_object_object_get_ex(usage, "sample_interval_seconds", &temp))
            g_config.usage_monitor.sample_interval_seconds = json_object_get_int(temp);
        
        if (json_object_object_get_ex(usage, "threshold_minutes", &temp))
            g_config.usage_monitor.threshold_minutes = json_object_get_int(temp);
        
        struct json_object* blacklist = NULL;
        if (json_object_object_get_ex(usage, "blacklist_apps", &blacklist)) {
            int array_size = json_object_array_length(blacklist);
            g_config.usage_monitor.blacklist_count = array_size;
            g_config.usage_monitor.blacklist_apps = malloc(sizeof(char*) * array_size);
            
            for (int i = 0; i < array_size; i++) {
                struct json_object* item = json_object_array_get_idx(blacklist, i);
                g_config.usage_monitor.blacklist_apps[i] = strdup(json_object_get_string(item));
            }
        }
    }
    
    struct json_object* llm = NULL;
    if (json_object_object_get_ex(root, "llm", &llm)) {
        struct json_object* temp = NULL;
        
        if (json_object_object_get_ex(llm, "enabled", &temp))
            g_config.llm.enabled = json_object_get_boolean(temp);
        
        if (json_object_object_get_ex(llm, "model_name", &temp)) {
            if (g_config.llm.model_name) free(g_config.llm.model_name);
            g_config.llm.model_name = strdup(json_object_get_string(temp));
        }
        
        if (json_object_object_get_ex(llm, "endpoint", &temp)) {
            if (g_config.llm.endpoint) free(g_config.llm.endpoint);
            g_config.llm.endpoint = strdup(json_object_get_string(temp));
        }
    }
    
    json_object_put(root);
    LOG_INFO("config", "Configuration loaded from %s", config_path);
    return 0;
}

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
    
    if (config_load_json(config_path) == 0) {
        LOG_INFO("config", "Configuration loaded successfully");
    } else {
        LOG_INFO("config", "Using default configuration");
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
