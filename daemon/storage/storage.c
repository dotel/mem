#include <stdlib.h>
#include <string.h>
#include "../../include/hari_storage.h"
#include "../../include/hari_log.h"

static storage_backend_t* g_backend = NULL;

int storage_init(const char* data_dir) {
    g_backend = storage_get_local_backend();
    
    if (!g_backend) {
        LOG_ERROR("storage", "Failed to get storage backend");
        return -1;
    }
    
    LOG_INFO("storage", "Storage initialized with data dir: %s", data_dir);
    return 0;
}

int storage_save_state(hari_state_t* state) {
    if (!g_backend || !g_backend->save_state) {
        LOG_ERROR("storage", "No storage backend available");
        return -1;
    }
    
    return g_backend->save_state(state);
}

int storage_load_state(hari_state_t* state) {
    if (!g_backend || !g_backend->load_state) {
        LOG_ERROR("storage", "No storage backend available");
        return -1;
    }
    
    return g_backend->load_state(state);
}

int storage_append_event(hari_event_t* event) {
    if (!g_backend || !g_backend->append_event) {
        LOG_ERROR("storage", "No storage backend available");
        return -1;
    }
    
    return g_backend->append_event(event);
}

void storage_shutdown(void) {
    LOG_INFO("storage", "Storage shutdown");
    g_backend = NULL;
}
