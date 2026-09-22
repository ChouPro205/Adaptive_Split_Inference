/*
 * GPIO timing markers for the PCA10059 measurement header.
 */

#ifndef ADAPTIVE_SPLIT_MARKERS_H_
#define ADAPTIVE_SPLIT_MARKERS_H_

#include <stdbool.h>

enum marker_id {
	MARKER_HEAD = 0,
	MARKER_PROTECTION,
	MARKER_TX,
	MARKER_WAIT,
	MARKER_COUNT
};

/* Configure every marker as an output driven LOW. */
int markers_init(void);

/* Each call performs exactly one write to the GPIO Port 0 set/clear register. */
void marker_on(enum marker_id marker);
void marker_off(enum marker_id marker);

/* Run the non-blocking 500 ms-per-marker hardware self-test. */
void markers_self_test_start(void);
void markers_self_test_update(bool log_enabled);

const char *marker_name(enum marker_id marker);
enum marker_id markers_self_test_active(void);

#endif /* ADAPTIVE_SPLIT_MARKERS_H_ */
