/*
 * Week 11 echo frames (W11-D2), portable C without Zephyr, host-tested against week11_common.py
 * (echo_frame, ack_frame) by device/scripts/test_week11_host.py:
 *   echo frame   I1 v2 envelope of total_length B (36..6380): magic I1PK, version 2, type 0x01, flags 0,
 *                header_length 32, reserved_0 (offset 10) = the answer asked for (1 = ECHO-ACK v1, 0 = the
 *                whole frame), no metadata/nonce, payload byte i = (i ^ (i >> 8) ^ request_id) & 0xff,
 *                CRC-32/ISO-HDLC. Valid at stage A of I1 v2 §7.1 (it does not read reserved_0), so binding
 *                v1 §9 echo peers accept it.
 *   ECHO-ACK v1  72-byte I1 v2 envelope from the KV260: type 0x02, request_id of the received frame, payload
 *                = uint32 LE length of the received frame + SHA-256 of the received frame, CRC-32.
 */
#ifndef WEEK11_ECHO_FRAMES_H
#define WEEK11_ECHO_FRAMES_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define ECHO_FRAME_MIN 36u
#define ECHO_FRAME_MAX 6380u
#define ECHO_ACK_LENGTH 72u
#define ECHO_MODE_FULL 0u
#define ECHO_MODE_ACK 1u

/* Writes the echo frame of length bytes into out (capacity >= length); returns length, 0 on error. */
size_t echo_frame_build(uint8_t *out, size_t capacity, uint16_t length, uint32_t request_id, bool ack);
/* The ECHO-ACK v1 the peer must send for sent[0..sent_length). */
void echo_ack_build(const uint8_t *sent, size_t sent_length, uint8_t out[ECHO_ACK_LENGTH]);
/* true when ack is exactly echo_ack_build(sent). */
bool echo_ack_check(const uint8_t *ack, size_t ack_length, const uint8_t *sent, size_t sent_length);

#endif
