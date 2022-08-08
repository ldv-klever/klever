/*
 * Copyright (c) 2022 ISP RAS (http://www.ispras.ru)
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

#include <ldv/common/list.h>
#include <ldv/linux/input.h>
#include <ldv/verifier/nondet.h>

int ldv_input_ff_create_memless(struct input_dev *dev, void *data, int (*play_effect)(struct input_dev *, void *, struct ff_effect *))
{
	int ret;

	/* NOTE Create memoryless force-feedback device in the nondeterministic way */
	ret = ldv_undef_int_nonpositive();

	if (!ret) {
		/* NOTE Store pointer to driver-specific data to global list (driver should not explicitly free related memory) */
		ldv_save_allocated_memory_to_list(data);
		/* NOTE Successfully created memoryless force-feedback device */
		return 0;
	}
	else {
		/* NOTE Could not create memoryless force-feedback device */
		return ret;
	}
}
