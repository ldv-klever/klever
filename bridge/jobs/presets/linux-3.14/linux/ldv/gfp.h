#ifndef __LINUX_LDV_GFP_H
#define __LINUX_LDV_GFP_H

#include <linux/gfp.h>

#ifdef LDV_BITWISE
# define CHECK_WAIT_FLAGS(flags) (!(flags & __GFP_WAIT))
#else
# define CHECK_WAIT_FLAGS(flags) ((flags == GFP_ATOMIC) || (flags == GFP_NOWAIT))
#endif /* LDV_BITWISE */

#endif /* __LINUX_LDV_GFP_H */
