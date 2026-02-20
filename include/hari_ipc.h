#ifndef HARI_IPC_H
#define HARI_IPC_H

#include <stddef.h>

#define IPC_PROTOCOL_VERSION 1
#define IPC_MAX_MESSAGE_SIZE 4096

typedef struct {
    int version;
    char type[64];
    char payload[512];
} ipc_request_t;

typedef struct {
    int version;
    char status[32];
    char message[512];
} ipc_response_t;

int ipc_server_init(const char* socket_path);
int ipc_server_poll(void);
void ipc_server_shutdown(void);

int ipc_client_connect(const char* socket_path);
int ipc_client_send(const char* request_json, char* response_buffer, size_t buffer_size);
void ipc_client_disconnect(void);

int ipc_parse_request(const char* json_str, ipc_request_t* request);
int ipc_serialize_response(ipc_response_t* response, char* buffer, size_t buffer_size);

#endif
