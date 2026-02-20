#ifndef HARI_LOG_H
#define HARI_LOG_H

#include <stdio.h>

typedef enum {
    LOG_DEBUG,
    LOG_INFO,
    LOG_WARN,
    LOG_ERROR
} log_level_t;

void log_init(log_level_t level);
void log_message(log_level_t level, const char* module, const char* fmt, ...);

#define LOG_DEBUG(module, ...) log_message(LOG_DEBUG, module, __VA_ARGS__)
#define LOG_INFO(module, ...) log_message(LOG_INFO, module, __VA_ARGS__)
#define LOG_WARN(module, ...) log_message(LOG_WARN, module, __VA_ARGS__)
#define LOG_ERROR(module, ...) log_message(LOG_ERROR, module, __VA_ARGS__)

#endif
