#ifndef HARI_COMMAND_H
#define HARI_COMMAND_H

#include "hari_ipc.h"

int command_dispatch(ipc_request_t* request, ipc_response_t* response);

#endif
