/* Host shim for test_week11_host.py / check_week11.py: the plan digest computed with link_plan_bytes.h + week 6
 * SHA-256 exactly as link_plan_digest() on the dongle (week11_link_plan.h of the session on the include path),
 * and the echo frame / ECHO-ACK v1 builders of echo_frames.c. */
#include <stdint.h>
#include <string.h>

#include "echo_frames.h"
#include "link_plan_bytes.h"

#if defined(_WIN32)
#define SHIM_EXPORT __declspec(dllexport)
#else
#define SHIM_EXPORT
#endif

SHIM_EXPORT unsigned shim_plan_entries(void)
{
	return WEEK11_LINK_PLAN_ENTRIES;
}

SHIM_EXPORT unsigned shim_plan_session(void)
{
	return WEEK11_LINK_PLAN_SESSION;
}

SHIM_EXPORT const char *shim_plan_sha256(void)
{
	return WEEK11_LINK_PLAN_SHA256;
}

SHIM_EXPORT void shim_plan_digest(char out[65])
{
	link_plan_digest_hex(out);
}

SHIM_EXPORT unsigned shim_echo_frame(uint8_t *out, unsigned capacity, unsigned length, uint32_t request_id, int ack)
{
	return (unsigned)echo_frame_build(out, capacity, (uint16_t)length, request_id, ack != 0);
}

SHIM_EXPORT void shim_echo_ack(const uint8_t *sent, unsigned sent_length, uint8_t *out)
{
	echo_ack_build(sent, sent_length, out);
}

SHIM_EXPORT int shim_echo_ack_check(const uint8_t *ack, unsigned ack_length, const uint8_t *sent, unsigned sent_length)
{
	return echo_ack_check(ack, ack_length, sent, sent_length) ? 1 : 0;
}
