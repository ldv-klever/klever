/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>


struct urb;

/* LDV_COMMENT_CHANGE_STATE Initialize allocated urb counter to zero. */
int ldv_urb_state = 0;

/* MODEL_FUNC_DEF Allocates memory for urb request. */
struct urb *ldv_usb_alloc_urb(void)
{
	/* OTHER Choose an arbitrary memory location. */
	void *arbitrary_memory = ldv_undef_ptr();
	/* OTHER If memory is not available. */
	if (!arbitrary_memory) {
		/* RETURN Failed to allocate memory. */
		return arbitrary_memory;
	}
	/* CHANGE_STATE Increase allocated counter. */
	ldv_urb_state += 1;
	/* RETURN The memory is successfully allocated. */
	return arbitrary_memory;
}

/* MODEL_FUNC_DEF Releases memory of urb request. */
void ldv_usb_free_urb(struct urb *urb) {
	if (urb) {
		/* ASSERT The memory must be allocated before. */
		ldv_assert("linux:usb:urb::less initial decrement", ldv_urb_state>=1);
		/* CHANGE_STATE Decrease allocated counter. */
		ldv_urb_state -= 1;
	}
}

/* MODEL_FUNC_DEF Check that all URB reference counters are not incremented at the end */
void ldv_check_final_state( void )
{
	/* ASSERT The urb requests must be freed at the end. */
	ldv_assert("linux:usb:urb::more initial at exit", ldv_urb_state==0);
}
