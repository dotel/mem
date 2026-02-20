#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/hari_types.h"
#include "../include/hari_ipc.h"
#include "socket_client.h"

void print_usage(const char* program) {
    printf("Usage: %s <command>\n", program);
    printf("\nCommands:\n");
    printf("  ping                 - Check if daemon is running\n");
    printf("  pomodoro start       - Start a Pomodoro session\n");
    printf("  pomodoro stop        - Stop current Pomodoro session\n");
    printf("  status               - Get daemon status\n");
    printf("  shutdown             - Shutdown the daemon\n");
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        print_usage(argv[0]);
        return 1;
    }
    
    if (ipc_client_connect(HARI_SOCKET_PATH) != 0) {
        fprintf(stderr, "Error: Cannot connect to Hari daemon. Is it running?\n");
        return 1;
    }
    
    char request[IPC_MAX_MESSAGE_SIZE];
    char response[IPC_MAX_MESSAGE_SIZE];
    
    if (strcmp(argv[1], "ping") == 0) {
        snprintf(request, sizeof(request), 
                 "{\"version\": %d, \"type\": \"ping\", \"payload\": \"\"}", 
                 IPC_PROTOCOL_VERSION);
    } else if (strcmp(argv[1], "pomodoro") == 0 && argc > 2) {
        snprintf(request, sizeof(request), 
                 "{\"version\": %d, \"type\": \"pomodoro\", \"payload\": \"%s\"}", 
                 IPC_PROTOCOL_VERSION, argv[2]);
    } else if (strcmp(argv[1], "status") == 0) {
        snprintf(request, sizeof(request), 
                 "{\"version\": %d, \"type\": \"status\", \"payload\": \"\"}", 
                 IPC_PROTOCOL_VERSION);
    } else {
        fprintf(stderr, "Unknown command: %s\n", argv[1]);
        print_usage(argv[0]);
        ipc_client_disconnect();
        return 1;
    }
    
    if (ipc_client_send(request, response, sizeof(response)) == 0) {
        printf("%s\n", response);
    } else {
        fprintf(stderr, "Error: Failed to communicate with daemon\n");
        ipc_client_disconnect();
        return 1;
    }
    
    ipc_client_disconnect();
    return 0;
}
