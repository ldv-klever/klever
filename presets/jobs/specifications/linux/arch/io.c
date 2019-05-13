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

int ldv_iomem = 0;

/* MODEL_FUNC Create some io-memory map for specified address */
void *ldv_io_mem_remap(void)
{
	void *ptr = ldv_undef_ptr();
	/* NOTE Choose an arbitrary return value. */
	if (ptr != 0) {
		/* NOTE Increase allocated counter. */
		ldv_iomem++;
		/* NOTE io-memory was successfully allocated. */
		return ptr;
	}
	/* NOTE io-memory was not allocated */
	return ptr;
}

/* MODEL_FUNC Delete some io-memory map for specified address */
void ldv_io_mem_unmap(void)
{
	/* ASSERT io-memory should be alloctaed before release */
	ldv_assert("linux:arch:io::less initial decrement", ldv_iomem >= 1);
	/* NOTE Decrease allocated counter. */
	ldv_iomem--;
}

/* MODEL_FUNC Check that all io-memory map are unmapped properly */
void ldv_check_final_state(void)
{
	/* ASSERT io-memory should be released at exit */
	ldv_assert("linux:arch:io::more initial at exit", ldv_iomem == 0);
}
