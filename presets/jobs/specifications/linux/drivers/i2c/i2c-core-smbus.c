/*
 * Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

#include <linux/types.h>
#include <linux/i2c.h>
#include <ldv/linux/i2c.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/memory.h>
#include <ldv/verifier/nondet.h>

s32 ldv_i2c_smbus_read_block_data(u8 *values)
{
	__u8 size;
	char *bytes;

	if (ldv_undef_int())
	{
		/* NOTE Determine the number of bytes to be read nondeterministically */
		size = ldv_undef_int_positive();
		/* NOTE SMBus allows to read 32 (I2C_SMBUS_BLOCK_MAX) bytes at most */
		ldv_assume(size <= I2C_SMBUS_BLOCK_MAX);
		/* NOTE "Read" bytes */
		bytes = ldv_xmalloc(size);
		/* NOTE Copy read bytes to buffer */
		__VERIFIER_memcpy(values, bytes, size);
		ldv_free(bytes);
		/* NOTE Return the number of read bytes */
		return size;
	}
	else
		/* NOTE Could not read I2C SMBus data */
		return ldv_undef_int_negative();
}
