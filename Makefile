CC = gcc
CFLAGS = -Wall -Wextra -std=c11 -I./include -g
LDFLAGS = -lpthread -ljson-c

DAEMON_SOURCES = daemon/main.c \
                 daemon/event_loop.c \
                 daemon/module_registry.c \
                 daemon/command_handler.c \
                 daemon/storage/storage.c \
                 daemon/storage/storage_local.c \
                 daemon/storage/storage_sync.c \
                 daemon/hari_log.c \
                 config/config.c \
                 modules/pomodoro/pomodoro.c \
                 modules/usage_monitor/usage_monitor.c \
                 modules/telegram/telegram.c \
                 modules/llm_adapter/llm_adapter.c \
                 ipc/socket_server.c \
                 ipc/socket_protocol.c

CLI_SOURCES = cli/main.c \
              cli/socket_client.c

DAEMON_OBJECTS = $(DAEMON_SOURCES:.c=.o)
CLI_OBJECTS = $(CLI_SOURCES:.c=.o)

DAEMON_TARGET = harid
CLI_TARGET = hari

.PHONY: all clean install

all: $(DAEMON_TARGET) $(CLI_TARGET)

$(DAEMON_TARGET): $(DAEMON_OBJECTS)
	$(CC) $(DAEMON_OBJECTS) -o $@ $(LDFLAGS)

$(CLI_TARGET): $(CLI_OBJECTS)
	$(CC) $(CLI_OBJECTS) -o $@

%.o: %.c
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f $(DAEMON_OBJECTS) $(CLI_OBJECTS) $(DAEMON_TARGET) $(CLI_TARGET)
	rm -f /tmp/hari.sock

install: $(DAEMON_TARGET) $(CLI_TARGET)
	install -m 755 $(DAEMON_TARGET) /usr/local/bin/
	install -m 755 $(CLI_TARGET) /usr/local/bin/

run: $(DAEMON_TARGET)
	./$(DAEMON_TARGET)

test: $(CLI_TARGET) $(DAEMON_TARGET)
	./$(DAEMON_TARGET) &
	sleep 1
	./$(CLI_TARGET) ping
	killall $(DAEMON_TARGET)
