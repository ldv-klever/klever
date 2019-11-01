/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
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
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>


struct urb;

/* NOTE Initialize allocated urb counter to zero. */
int ldv_urb_state = 0;

/* MODEL_FUNC Allocates memory for urb request. */
struct urb *ldv_usb_alloc_urb(void)
{
	/* NOTE Choose an arbitrary memory location. */
	void *arbitrary_memory = ldv_undef_ptr();
	/* NOTE If memory is not available. */
	if (!arbitrary_memory) {
		/* NOTE Failed to allocate memory. */
		return arbitrary_memory;
	}
	/* NOTE Increase allocated counter. */
	ldv_urb_state += 1;
	/* NOTE The memory is successfully allocated. */
	return arbitrary_memory;
}

/* MODEL_FUNC Allocates memory for urb request. */
struct urb *ldv_usb_get_urb(struct urb *urb)
{
	if (urb) {
		/* ASSERT The memory must be allocated before. */
		ldv_assert(ldv_urb_state>=1);
		/* NOTE Increase allocated counter. */
		ldv_urb_state += 1;
		return urb;
	}
}

/* MODEL_FUNC Releases memory of urb request. */
void ldv_usb_free_urb(struct urb *urb) {
	if (urb) {
		/* ASSERT The memory must be allocated before. */
		ldv_assert(ldv_urb_state>=1);
		/* NOTE Decrease allocated counter. */
		ldv_urb_state -= 1;
	}
}

/* MODEL_FUNC Check that all URB reference counters are not incremented at the end */
void ldv_check_final_state( void )
{
	/* ASSERT The urb requests must be freed at the end. */
	ldv_assert(ldv_urb_state==0);
}
