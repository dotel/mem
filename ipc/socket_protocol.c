#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <json-c/json.h>
#include "../include/hari_ipc.h"
#include "../include/hari_log.h"

int ipc_parse_request(const char* json_str, ipc_request_t* request) {
    struct json_object* root = json_tokener_parse(json_str);
    if (!root) {
        LOG_ERROR("ipc_protocol", "Failed to parse JSON request");
        return -1;
    }
    
    struct json_object* version_obj = NULL;
    struct json_object* type_obj = NULL;
    struct json_object* payload_obj = NULL;
    
    if (!json_object_object_get_ex(root, "version", &version_obj) ||
        !json_object_object_get_ex(root, "type", &type_obj)) {
        LOG_ERROR("ipc_protocol", "Missing required fields in request");
        json_object_put(root);
        return -1;
    }
    
    request->version = json_object_get_int(version_obj);
    
    const char* type_str = json_object_get_string(type_obj);
    if (type_str) {
        strncpy(request->type, type_str, sizeof(request->type) - 1);
        request->type[sizeof(request->type) - 1] = '\0';
    }
    
    if (json_object_object_get_ex(root, "payload", &payload_obj)) {
        const char* payload_str = json_object_get_string(payload_obj);
        if (payload_str) {
            strncpy(request->payload, payload_str, sizeof(request->payload) - 1);
            request->payload[sizeof(request->payload) - 1] = '\0';
        } else {
            request->payload[0] = '\0';
        }
    } else {
        request->payload[0] = '\0';
    }
    
    json_object_put(root);
    
    if (request->version != IPC_PROTOCOL_VERSION) {
        LOG_WARN("ipc_protocol", "Protocol version mismatch: expected %d, got %d", 
                 IPC_PROTOCOL_VERSION, request->version);
    }
    
    return 0;
}

int ipc_serialize_response(ipc_response_t* response, char* buffer, size_t buffer_size) {
    struct json_object* root = json_object_new_object();
    
    json_object_object_add(root, "version", json_object_new_int(response->version));
    json_object_object_add(root, "status", json_object_new_string(response->status));
    json_object_object_add(root, "message", json_object_new_string(response->message));
    
    const char* json_str = json_object_to_json_string_ext(root, JSON_C_TO_STRING_PLAIN);
    if (!json_str) {
        json_object_put(root);
        return -1;
    }
    
    snprintf(buffer, buffer_size, "%s", json_str);
    
    json_object_put(root);
    return 0;
}
