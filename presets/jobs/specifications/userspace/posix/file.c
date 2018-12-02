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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <verifier/common.h>
#include <verifier/nondet.h>

/* Files reference counter that shouldn't go lower its initial state. We do not distinguish different files. */
/* NOTE Set files reference counter initial value at the beginning */
int ldv_file_refcounter = 1;

/* MODEL_FUNC Increment opened files reference counter unless the file descriptor is NULL */
int ldv_open(const char *pathname, int flags)
{
    if (ldv_undef_int()) {
        /* NOTE Increment module reference counter according to the successful open */
		ldv_file_refcounter++;
		return ldv_undef_int_positive();
    } else {
        /* NOTE Open has failed */
		return 0;
    }
}

/* MODEL_FUNC Close the file */
int ldv_close(int fd)
{
	/* NOTE Decrease files reference counter */
	ldv_file_refcounter--;
	// todo: this is not precise
	return 0;
}

/* MODEL_FUNC Check that files reference counter has its initial value at the end */
void ldv_check_final_state(void)
{
	/* ASSERT Files reference counter should be decremented to its initial value before finishing operation */
	ldv_assert("userspace:posix::open", ldv_file_refcounter == 1);
}
