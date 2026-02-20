#ifndef HARI_CONFIG_H
#define HARI_CONFIG_H

#include <stdint.h>
#include <stdbool.h>

typedef struct {
    struct {
        uint32_t duration_minutes;
        uint32_t short_break_minutes;
        uint32_t long_break_minutes;
        bool auto_start_breaks;
    } pomodoro;
    
    struct {
        char* token;
        char* chat_id;
        bool enabled;
    } telegram;
    
    struct {
        uint32_t sample_interval_seconds;
        char** blacklist_apps;
        uint32_t blacklist_count;
        uint32_t threshold_minutes;
    } usage_monitor;
    
    struct {
        char* model_name;
        char* endpoint;
        bool enabled;
    } llm;
} hari_config_t;

int config_init(const char* config_path);
hari_config_t* config_get(void);
void config_free(void);

#endif
