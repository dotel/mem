#include <stdlib.h>
#include <string.h>
#include "../include/hari_types.h"
#include "../include/hari_log.h"

#define MAX_EVENT_QUEUE 256

typedef struct {
    hari_event_t events[MAX_EVENT_QUEUE];
    int head;
    int tail;
    int count;
} event_queue_t;

static event_queue_t g_event_queue = {0};

int event_queue_init(void) {
    g_event_queue.head = 0;
    g_event_queue.tail = 0;
    g_event_queue.count = 0;
    return 0;
}

int event_queue_push(hari_event_t* event) {
    if (g_event_queue.count >= MAX_EVENT_QUEUE) {
        LOG_ERROR("event_queue", "Event queue full, dropping event");
        return -1;
    }
    
    g_event_queue.events[g_event_queue.tail] = *event;
    g_event_queue.tail = (g_event_queue.tail + 1) % MAX_EVENT_QUEUE;
    g_event_queue.count++;
    
    return 0;
}

hari_event_t* event_queue_pop(void) {
    if (g_event_queue.count == 0) {
        return NULL;
    }
    
    hari_event_t* event = &g_event_queue.events[g_event_queue.head];
    g_event_queue.head = (g_event_queue.head + 1) % MAX_EVENT_QUEUE;
    g_event_queue.count--;
    
    return event;
}

int event_queue_size(void) {
    return g_event_queue.count;
}
