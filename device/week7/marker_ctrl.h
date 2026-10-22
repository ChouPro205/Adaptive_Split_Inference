/*
 * Fifth GPIO marker D4 = CTRL on P0.22 (decision W7-D4), next to D3 = P0.20 on the
 * castellated edge. src/markers.c (D0-D3) is hash-locked, so D4 lives here; it uses the same
 * Port 0 OUTSET/OUTCLR single-write scheme so every marker edge costs one register write.
 */
#ifndef WEEK7_MARKER_CTRL_H
#define WEEK7_MARKER_CTRL_H

#define MARKER_CTRL_PIN 22U

/* Configure P0.22 as an output driven LOW. */
int marker_ctrl_init(void);
void marker_ctrl_on(void);
void marker_ctrl_off(void);

#endif
