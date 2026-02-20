#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../include/hari_ipc.h"
#include "../include/hari_log.h"

int ipc_parse_request(const char* json, ipc_request_t* request) {
    LOG_INFO("ipc_protocol", "TODO: Implement JSON parsing");
    return 0;
}

int ipc_serialize_response(ipc_response_t* response, char* buffer, size_t buffer_size) {
    snprintf(buffer, buffer_size, 
             "{\"version\": %d, \"status\": \"%s\", \"message\": \"%s\"}", 
             response->version, response->status, response->message);
    return 0;
}
