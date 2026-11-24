//
// Doom for the Compaq's own dots: the game runs here on the Pi at its usual
// speed, and hands over a frame only when asked, as plain grey bytes, so the
// Pi can dither it and send it down the Compaq's cable (see lib/doomhd.py).
// Keys arrive as "this key went down" and "this key came up", which is what
// the Compaq's keyboard reports through PILINK: keys can be held.
//
// It takes the place of doomgeneric_ascii.c in doom-ascii's source
// (github.com/wojciech-graj/doom-ascii, GPL-2.0-or-later, as is this file);
// fetch-net.sh builds it as /opt/compaq-net/bin/doom-frames.
//
// Commands, on standard input:
//   F        send the next frame drawn: RESX * RESY bytes of grey (0 dark to
//            255 bright), row by row, on the file descriptor whose number is
//            in the environment as DOOM_FRAMES_FD
//   D key    a key went down (key: one byte, Doom's own code for it)
//   U key    a key came up
// Standard input closing ends the game.
//

#include "doomgeneric.h"
#include "doomkeys.h"
#include "i_system.h"

#include <errno.h>
#include <fcntl.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <unistd.h>

#define QUEUE 64

static struct timespec started;
static int frame_fd = 3, frame_wanted;
static unsigned char *grey;
static struct { unsigned char key, pressed; } keys[QUEUE];
static unsigned head, tail;
static unsigned char partial;     /* a D or U whose key hasn't arrived yet */

void DG_Init(void)
{
	const char *const fd = getenv("DOOM_FRAMES_FD");
	if (fd)
		frame_fd = atoi(fd);
	clock_gettime(CLOCK_MONOTONIC, &started);
	grey = malloc((size_t)DOOMGENERIC_RESX * DOOMGENERIC_RESY);
	fcntl(STDIN_FILENO, F_SETFL, fcntl(STDIN_FILENO, F_GETFL) | O_NONBLOCK);
}

void DG_DrawFrame(void)
{
	if (!frame_wanted)
		return;
	frame_wanted = 0;
	const size_t count = (size_t)DOOMGENERIC_RESX * DOOMGENERIC_RESY;
	for (size_t i = 0; i < count; i++) {
		const uint32_t p = DG_ScreenBuffer[i];
		grey[i] = (unsigned char)((((p >> 16) & 0xff) * 77 + ((p >> 8) & 0xff) * 150
			+ (p & 0xff) * 29) >> 8);
	}
	size_t sent = 0;
	while (sent < count) {
		const ssize_t n = write(frame_fd, grey + sent, count - sent);
		if (n < 0 && errno == EINTR)
			continue;
		if (n <= 0)
			exit(0);          /* nobody is watching any more */
		sent += (size_t)n;
	}
}

void DG_SleepMs(const uint32_t ms)
{
	const struct timespec t = { ms / 1000, (long)(ms % 1000) * 1000000L };
	nanosleep(&t, NULL);
}

uint32_t DG_GetTicksMs(void)
{
	struct timespec now;
	clock_gettime(CLOCK_MONOTONIC, &now);
	return (uint32_t)((now.tv_sec - started.tv_sec) * 1000
		+ (now.tv_nsec - started.tv_nsec) / 1000000);
}

void DG_ReadInput(void)
{
	unsigned char buffer[256];
	for (;;) {
		const ssize_t n = read(STDIN_FILENO, buffer, sizeof buffer);
		if (n == 0)
			exit(0);          /* whoever started us has gone */
		if (n < 0)
			return;           /* nothing more for now */
		for (ssize_t i = 0; i < n; i++) {
			const unsigned char c = buffer[i];
			if (partial) {
				if ((head + 1) % QUEUE != tail) {
					keys[head].key = c;
					keys[head].pressed = partial == 'D';
					head = (head + 1) % QUEUE;
				}
				partial = 0;
			} else if (c == 'F') {
				frame_wanted = 1;
			} else if (c == 'D' || c == 'U') {
				partial = c;
			}
		}
	}
}

int DG_GetKey(int *const pressed, unsigned char *const key)
{
	if (head == tail)
		return 0;
	*pressed = keys[tail].pressed;
	*key = keys[tail].key;
	tail = (tail + 1) % QUEUE;
	return 1;
}

void DG_SetWindowTitle(const char *const title)
{
	(void)title;
}
