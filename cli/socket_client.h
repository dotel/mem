#ifndef SOCKET_CLIENT_H
#define SOCKET_CLIENT_H

#include <stddef.h>

int ipc_client_connect(const char* socket_path);
int ipc_client_send(const char* request_json, char* response_buffer, size_t buffer_size);
void ipc_client_disconnect(void);

#endif
