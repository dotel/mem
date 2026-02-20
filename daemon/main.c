#define _POSIX_C_SOURCE 199309L
#define _DEFAULT_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <signal.h>
#include <unistd.h>
#include <string.h>
#include <sys/stat.h>
#include <time.h>
#include "../include/hari_types.h"
#include "../include/hari_log.h"
#include "../include/hari_config.h"
#include "../include/hari_module.h"
#include "../include/hari_storage.h"
#include "../include/hari_ipc.h"

static volatile bool g_running = true;
static hari_state_t g_state = {0};

void signal_handler(int signum) {
    LOG_INFO("main", "Received signal %d, shutting down...", signum);
    g_running = false;
}

void setup_signal_handlers(void) {
    signal(SIGINT, signal_handler);
    signal(SIGTERM, signal_handler);
}

int ensure_config_dir(void) {
    char config_path[256];
    snprintf(config_path, sizeof(config_path), "%s/%s", getenv("HOME"), HARI_CONFIG_DIR);
    
    struct stat st = {0};
    if (stat(config_path, &st) == -1) {
        if (mkdir(config_path, 0755) != 0) {
            LOG_ERROR("main", "Failed to create config directory: %s", config_path);
            return -1;
        }
        LOG_INFO("main", "Created config directory: %s", config_path);
    }
    return 0;
}

uint64_t get_time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000 + (uint64_t)ts.tv_nsec / 1000000;
}

extern hari_module_t* pomodoro_module_create(void);
extern hari_module_t* usage_monitor_module_create(void);
extern hari_module_t* telegram_module_create(void);
extern hari_module_t* llm_adapter_module_create(void);

int main(int argc, char* argv[]) {
    log_init(LOG_INFO);
    LOG_INFO("main", "Hari daemon v%s starting...", HARI_VERSION);
    
    if (ensure_config_dir() != 0) {
        return 1;
    }
    
    char config_file[256];
    snprintf(config_file, sizeof(config_file), "%s/%s/config.toml", 
             getenv("HOME"), HARI_CONFIG_DIR);
    
    if (config_init(config_file) != 0) {
        LOG_WARN("main", "Failed to load config, using defaults");
    }
    
    char data_dir[256];
    snprintf(data_dir, sizeof(data_dir), "%s/%s", getenv("HOME"), HARI_CONFIG_DIR);
    
    if (storage_init(data_dir) != 0) {
        LOG_ERROR("main", "Failed to initialize storage");
        return 1;
    }
    
    if (storage_load_state(&g_state) != 0) {
        LOG_INFO("main", "No previous state found, starting fresh");
        g_state.start_time = time(NULL);
    }
    
    if (module_registry_init() != 0) {
        LOG_ERROR("main", "Failed to initialize module registry");
        return 1;
    }
    
    hari_module_t* pomodoro = pomodoro_module_create();
    hari_module_t* usage_monitor = usage_monitor_module_create();
    hari_module_t* telegram = telegram_module_create();
    hari_module_t* llm_adapter = llm_adapter_module_create();
    
    if (pomodoro) module_register(pomodoro);
    if (usage_monitor) module_register(usage_monitor);
    if (telegram) module_register(telegram);
    if (llm_adapter) module_register(llm_adapter);
    
    LOG_INFO("main", "Registered %d modules", module_count());
    
    if (ipc_server_init(HARI_SOCKET_PATH) != 0) {
        LOG_ERROR("main", "Failed to initialize IPC server");
        return 1;
    }
    
    setup_signal_handlers();
    
    LOG_INFO("main", "Entering main event loop...");
    uint64_t last_save_time = get_time_ms();
    
    while (g_running) {
        uint64_t now = get_time_ms();
        g_state.uptime_ms = now;
        
        ipc_server_poll();
        
        module_tick_all(now);
        
        if (now - last_save_time > 60000) {
            storage_save_state(&g_state);
            last_save_time = now;
        }
        
        usleep(HARI_TICK_INTERVAL_MS * 1000);
    }
    
    LOG_INFO("main", "Shutting down...");
    
    storage_save_state(&g_state);
    module_shutdown_all();
    ipc_server_shutdown();
    storage_shutdown();
    config_free();
    
    LOG_INFO("main", "Hari daemon stopped");
    return 0;
}
