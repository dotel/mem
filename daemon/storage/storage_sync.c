#include <stdio.h>
#include "../../include/hari_storage.h"
#include "../../include/hari_log.h"

static int sync_save_state(hari_state_t* state) {
    LOG_INFO("storage_sync", "Sync backend not yet implemented");
    return -1;
}

static int sync_load_state(hari_state_t* state) {
    LOG_INFO("storage_sync", "Sync backend not yet implemented");
    return -1;
}

static int sync_append_event(hari_event_t* event) {
    LOG_INFO("storage_sync", "Sync backend not yet implemented");
    return -1;
}

static storage_backend_t sync_backend = {
    .save_state = sync_save_state,
    .load_state = sync_load_state,
    .append_event = sync_append_event
};

storage_backend_t* storage_get_sync_backend(void) {
    return &sync_backend;
}
