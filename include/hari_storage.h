#ifndef HARI_STORAGE_H
#define HARI_STORAGE_H

#include "hari_types.h"

int storage_init(const char* data_dir);
int storage_save_state(hari_state_t* state);
int storage_load_state(hari_state_t* state);
int storage_append_event(hari_event_t* event);
void storage_shutdown(void);

storage_backend_t* storage_get_local_backend(void);

#endif
