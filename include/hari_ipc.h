#ifndef HARI_IPC_H
#define HARI_IPC_H

#include <stddef.h>

#define IPC_PROTOCOL_VERSION 1
#define IPC_MAX_MESSAGE_SIZE 4096

typedef struct {
    int version;
    const char* type;
    const char* payload;
} ipc_request_t;

typedef struct {
    int version;
    const char* status;
    const char* message;
} ipc_response_t;

int ipc_server_init(const char* socket_path);
int ipc_server_poll(void);
void ipc_server_shutdown(void);

int ipc_client_connect(const char* socket_path);
int ipc_client_send(const char* request_json, char* response_buffer, size_t buffer_size);
void ipc_client_disconnect(void);

#endif
