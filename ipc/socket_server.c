#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/socket.h>
#include <sys/un.h>
#include <fcntl.h>
#include <errno.h>
#include "../include/hari_ipc.h"
#include "../include/hari_log.h"
#include "../include/hari_command.h"

static int g_server_fd = -1;
static char g_socket_path[256] = {0};

int ipc_server_init(const char* socket_path) {
    unlink(socket_path);
    
    g_server_fd = socket(AF_UNIX, SOCK_STREAM, 0);
    if (g_server_fd < 0) {
        LOG_ERROR("ipc_server", "Failed to create socket: %s", strerror(errno));
        return -1;
    }
    
    int flags = fcntl(g_server_fd, F_GETFL, 0);
    fcntl(g_server_fd, F_SETFL, flags | O_NONBLOCK);
    
    struct sockaddr_un addr;
    memset(&addr, 0, sizeof(addr));
    addr.sun_family = AF_UNIX;
    strncpy(addr.sun_path, socket_path, sizeof(addr.sun_path) - 1);
    
    if (bind(g_server_fd, (struct sockaddr*)&addr, sizeof(addr)) < 0) {
        LOG_ERROR("ipc_server", "Failed to bind socket: %s", strerror(errno));
        close(g_server_fd);
        return -1;
    }
    
    if (listen(g_server_fd, 5) < 0) {
        LOG_ERROR("ipc_server", "Failed to listen on socket: %s", strerror(errno));
        close(g_server_fd);
        return -1;
    }
    
    strncpy(g_socket_path, socket_path, sizeof(g_socket_path) - 1);
    LOG_INFO("ipc_server", "IPC server listening on %s", socket_path);
    return 0;
}

int ipc_server_poll(void) {
    if (g_server_fd < 0) {
        return -1;
    }
    
    int client_fd = accept(g_server_fd, NULL, NULL);
    if (client_fd < 0) {
        if (errno != EAGAIN && errno != EWOULDBLOCK) {
            LOG_ERROR("ipc_server", "Failed to accept connection: %s", strerror(errno));
        }
        return 0;
    }
    
    char buffer[IPC_MAX_MESSAGE_SIZE];
    ssize_t bytes_read = read(client_fd, buffer, sizeof(buffer) - 1);
    
    if (bytes_read > 0) {
        buffer[bytes_read] = '\0';
        LOG_DEBUG("ipc_server", "Received message: %s", buffer);
        
        ipc_request_t request = {0};
        ipc_response_t response = {0};
        
        if (ipc_parse_request(buffer, &request) == 0) {
            LOG_INFO("ipc_server", "Processing command: %s %s", request.type, request.payload);
            command_dispatch(&request, &response);
        } else {
            response.version = IPC_PROTOCOL_VERSION;
            strncpy(response.status, "error", sizeof(response.status) - 1);
            strncpy(response.message, "Failed to parse request", sizeof(response.message) - 1);
        }
        
        char response_buffer[IPC_MAX_MESSAGE_SIZE];
        if (ipc_serialize_response(&response, response_buffer, sizeof(response_buffer)) == 0) {
            write(client_fd, response_buffer, strlen(response_buffer));
        } else {
            const char* error_response = "{\"version\": 1, \"status\": \"error\", \"message\": \"Failed to serialize response\"}";
            write(client_fd, error_response, strlen(error_response));
        }
    }
    
    close(client_fd);
    return 0;
}

void ipc_server_shutdown(void) {
    if (g_server_fd >= 0) {
        close(g_server_fd);
        unlink(g_socket_path);
        LOG_INFO("ipc_server", "IPC server shutdown");
        g_server_fd = -1;
    }
}
