#ifndef HARI_MODULE_H
#define HARI_MODULE_H

#include "hari_types.h"

int module_registry_init(void);
int module_register(hari_module_t* module);
void module_tick_all(uint64_t now_ms);
void module_dispatch_event(hari_event_t* event);
void module_shutdown_all(void);
int module_count(void);

#endif
