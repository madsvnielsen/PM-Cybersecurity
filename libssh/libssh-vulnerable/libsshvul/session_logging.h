/* Logging instrumentation for the Linux ssh_server_fork example. */
#ifndef SESSION_LOGGING_H
#define SESSION_LOGGING_H

#include <errno.h>
#include <stdarg.h>
#include <stdio.h>
#include <string.h>
#include <sys/time.h>
#include <time.h>
#include <unistd.h>

static char session_run_id[37];
static char session_case_id[80] = "server";
static unsigned long long session_counter;

/* libssh supplies the function name inside buffer already. One write keeps
 * lines from different child processes together on Docker's shared pipe. */
static void session_log_callback(int priority, const char *function,
                                 const char *buffer, void *userdata)
{
    struct timeval now;
    struct tm utc;
    char date[32];
    char line[2048];
    int length;
    ssize_t written;

    (void) function;
    (void) userdata;
    gettimeofday(&now, NULL);
    gmtime_r(&now.tv_sec, &utc);
    strftime(date, sizeof(date), "%Y-%m-%dT%H:%M:%S", &utc);
    length = snprintf(line, sizeof(line),
                      "[%s.%06ldZ, %d] [case=%s] %s\n",
                      date, (long)now.tv_usec, priority, session_case_id, buffer);
    if (length < 0) {
        return;
    }
    if ((size_t)length >= sizeof(line)) {
        length = sizeof(line) - 1;
        line[length - 1] = '\n';
    }
    do {
        written = write(STDERR_FILENO, line, (size_t)length);
    } while (written < 0 && errno == EINTR);
}

static void session_logging_event(const char *message)
{
    char buffer[1200];
    snprintf(buffer, sizeof(buffer), "process_mining: %s", message);
    session_log_callback(1, "process_mining", buffer, NULL);
}

static void session_logging_error(const char *format, ...)
{
    char buffer[1024];
    size_t length;
    va_list args;
    va_start(args, format);
    vsnprintf(buffer, sizeof(buffer), format, args);
    va_end(args);
    length = strlen(buffer);
    while (length > 0 && (buffer[length - 1] == '\n' || buffer[length - 1] == '\r')) {
        buffer[--length] = '\0';
    }
    session_log_callback(0, "server_error", buffer, NULL);
}

static int session_logging_init(void)
{
    FILE *uuid = fopen("/proc/sys/kernel/random/uuid", "r");
    int scanned;
    if (uuid == NULL) {
        return SSH_ERROR;
    }
    scanned = fscanf(uuid, "%36[0-9a-f-]", session_run_id);
    fclose(uuid);
    if (scanned != 1 || strlen(session_run_id) != 36) {
        return SSH_ERROR;
    }
    snprintf(session_case_id, sizeof(session_case_id), "server-%s", session_run_id);
    return ssh_set_log_callback(session_log_callback);
}

/* Set this before accept: libssh can log while accepting, before fork().
 * The child inherits its own copy; future accepts only change the parent. */
static void session_logging_next_case(void)
{
    snprintf(session_case_id, sizeof(session_case_id), "%s-%llu",
             session_run_id, ++session_counter);
}

#endif
