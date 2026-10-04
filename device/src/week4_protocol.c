#include "week4_protocol.h"
#include "week4_head.h"
#include "week4_inputs.h"

#include <stddef.h>
#include <string.h>

static int parse_number(const char **cursor, unsigned limit, unsigned *number)
{
	const char *p = *cursor;
	unsigned value = 0;
	if (*p < '0' || *p > '9') {
		return -1;
	}
	do {
		value = value * 10U + (unsigned)(*p++ - '0');
		if (value >= limit) {
			return -1;
		}
	} while (*p >= '0' && *p <= '9');
	*cursor = p;
	*number = value;
	return 0;
}

int week4_parse_command(const char *line, struct week4_command *command)
{
	if (line == NULL || command == NULL) {
		return -1;
	}
	struct week4_command parsed = {0};
	const char *p;
	if (strncmp(line, "RUN ", 4) == 0) {
		parsed.type = WEEK4_RUN;
		p = line + 4;
	} else if (strncmp(line, "BENCH ", 6) == 0) {
		parsed.type = WEEK4_BENCH;
		p = line + 6;
	} else {
		return -1;
	}
	if (parse_number(&p, WEEK4_SAMPLE_COUNT, &parsed.sample) != 0 || *p++ != ' ' ||
	    parse_number(&p, WEEK4_SPLIT_COUNT, &parsed.split) != 0 || *p != '\0') {
		return -1;
	}
	*command = parsed;
	return 0;
}
