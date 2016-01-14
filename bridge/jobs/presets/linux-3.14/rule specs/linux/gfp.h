#ifndef _GFP_H
#define _GFP_H

#include <linux/kernel.h>

#ifdef LDV_BITWISE
# define CHECK_WAIT_FLAGS(flags) (!(flags & __GFP_WAIT))
#else
# define CHECK_WAIT_FLAGS(flags) ((flags == GFP_ATOMIC) || (flags == GFP_NOWAIT))
#endif /* LDV_BITWISE */

#endif /* _GFP_H */


