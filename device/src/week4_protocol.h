#ifndef WEEK4_PROTOCOL_H
#define WEEK4_PROTOCOL_H

enum week4_command_type { WEEK4_RUN, WEEK4_BENCH };
struct week4_command {
	enum week4_command_type type;
	unsigned sample;
	unsigned split;
};
int week4_parse_command(const char *line, struct week4_command *command);

#endif
