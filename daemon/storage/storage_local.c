#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include "../../include/hari_storage.h"
#include "../../include/hari_log.h"

static char g_state_file[512] = {0};
static char g_events_file[512] = {0};

static int local_save_state(hari_state_t* state) {
    if (strlen(g_state_file) == 0) {
        snprintf(g_state_file, sizeof(g_state_file), "%s/.hari/state.json", getenv("HOME"));
    }
    
    FILE* fp = fopen(g_state_file, "w");
    if (!fp) {
        LOG_ERROR("storage_local", "Failed to open state file for writing");
        return -1;
    }
    
    fprintf(fp, "{\n");
    fprintf(fp, "  \"uptime_ms\": %lu,\n", state->uptime_ms);
    fprintf(fp, "  \"event_count\": %u,\n", state->event_count);
    fprintf(fp, "  \"start_time\": %ld\n", state->start_time);
    fprintf(fp, "}\n");
    
    fclose(fp);
    LOG_DEBUG("storage_local", "State saved to %s", g_state_file);
    return 0;
}

static int local_load_state(hari_state_t* state) {
    if (strlen(g_state_file) == 0) {
        snprintf(g_state_file, sizeof(g_state_file), "%s/.hari/state.json", getenv("HOME"));
    }
    
    FILE* fp = fopen(g_state_file, "r");
    if (!fp) {
        LOG_INFO("storage_local", "No state file found, starting fresh");
        return -1;
    }
    
    fscanf(fp, "{\n");
    fscanf(fp, "  \"uptime_ms\": %lu,\n", &state->uptime_ms);
    fscanf(fp, "  \"event_count\": %u,\n", &state->event_count);
    fscanf(fp, "  \"start_time\": %ld\n", &state->start_time);
    
    fclose(fp);
    LOG_INFO("storage_local", "State loaded from %s", g_state_file);
    return 0;
}

static int local_append_event(hari_event_t* event) {
    if (strlen(g_events_file) == 0) {
        snprintf(g_events_file, sizeof(g_events_file), "%s/.hari/events.log", getenv("HOME"));
    }
    
    FILE* fp = fopen(g_events_file, "a");
    if (!fp) {
        LOG_ERROR("storage_local", "Failed to open events file for appending");
        return -1;
    }
    
    fprintf(fp, "{\"timestamp\": %lu, \"type\": %d}\n", event->timestamp_ms, event->type);
    fclose(fp);
    
    return 0;
}

static storage_backend_t local_backend = {
    .save_state = local_save_state,
    .load_state = local_load_state,
    .append_event = local_append_event
};

storage_backend_t* storage_get_local_backend(void) {
    return &local_backend;
}
