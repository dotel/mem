#include <stdio.h>
#include <stdlib.h>
#include <stdarg.h>
#include <time.h>
#include <string.h>
#include "../include/hari_log.h"

static log_level_t g_log_level = LOG_INFO;

static const char* log_level_str(log_level_t level) {
    switch (level) {
        case LOG_DEBUG: return "DEBUG";
        case LOG_INFO:  return "INFO ";
        case LOG_WARN:  return "WARN ";
        case LOG_ERROR: return "ERROR";
        default:        return "?????";
    }
}

void log_init(log_level_t level) {
    g_log_level = level;
}

void log_message(log_level_t level, const char* module, const char* fmt, ...) {
    if (level < g_log_level) {
        return;
    }
    
    time_t now = time(NULL);
    struct tm* tm_info = localtime(&now);
    char time_str[32];
    strftime(time_str, sizeof(time_str), "%Y-%m-%d %H:%M:%S", tm_info);
    
    fprintf(stderr, "[%s] [%s] [%s] ", time_str, log_level_str(level), module);
    
    va_list args;
    va_start(args, fmt);
    vfprintf(stderr, fmt, args);
    va_end(args);
    
    fprintf(stderr, "\n");
}
