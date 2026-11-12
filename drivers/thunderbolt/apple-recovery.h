/* SPDX-License-Identifier: GPL-2.0-only OR MIT */
#ifndef APPLE_USB4_RECOVERY_H
#define APPLE_USB4_RECOVERY_H

#define APPLE_CIO_LINK_LOST_CYCLES 3

/* One existing timer owns admission; no PD or board timer refills it. */
static inline unsigned int apple_cio_recovery_action(unsigned int cycles,
						    bool blocked, bool peer,
						    bool t6050)
{
	if (blocked || peer || cycles >= APPLE_CIO_LINK_LOST_CYCLES)
		return 0;
	return t6050 && cycles ? 2 : 1;
}
/* A new NHI starts at zero; its allocation is not remote progress. */
static inline bool apple_cio_recovery_progress(unsigned long long activity,
					       unsigned long long previous)
{
	return activity && activity != previous;
}
/* Only a live, discovered peer completes the old NHI's recovery epoch. */
static inline bool apple_cio_recovery_completed(bool peer,
					      unsigned long long activity)
{
	return peer && activity;
}
#endif
