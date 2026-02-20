#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <errno.h>
#include "socket_client.h"
#include "../include/hari_ipc.h"

static int g_client_fd = -1;

int ipc_client_connect(const char* socket_path) {
    g_client_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (g_client_fd < 0) {
        fprintf(stderr, "Failed to create socket: %s\n", strerror(errno));
        return -1;
    }
    
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path) - 1);
    
    if (connect(g_client_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        close(g_client_fd);
        g_client_fd = -1;
        return -1;
    }
    
    return 0;
}

int ipc_client_send(const char* request_json, char* response_buffer, size_t buffer_size) {
    if (g_client_fd < 0) {
        return -1;
    }
    
    ssize_t bytes_written = write(g_client_fd, request_json, strlen(request_json));
    if (bytes_written < 0) {
        fprintf(stderr, "Failed to send request: %s\n", strerror(errno));
        return -1;
    }
    
    ssize_t bytes_read = read(g_client_fd, response_buffer, buffer_size - 1);
    if (bytes_read < 0) {
        fprintf(stderr, "Failed to read response: %s\n", strerror(errno));
        return -1;
    }
    
    response_buffer[bytes_read] = '\0';
    return 0;
}

void ipc_client_disconnect(void) {
    if (g_client_fd >= 0) {
        close(g_client_fd);
        g_client_fd = -1;
    }
}
