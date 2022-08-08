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

#include <linux/types.h>
#include <linux/i2c.h>
#include <ldv/linux/i2c.h>
#include <ldv/verifier/nondet.h>

const struct i2c_device_id *ldv_i2c_match_id(const struct i2c_device_id *id, const struct i2c_client *client)
{
	int i, choice;

	/* The kernel stops to traverse table when this condition is satisfied. It corresponds to trailing terminating
	   initializer {}. EMG is aware about the corresponding array size statically. So it would be better to implement
       this model there (moreover, usually such the choices are made in the environment model). */
	for (i = 0; id[i].name[0]; i++);

	choice = ldv_undef_int_range(0, i - 1);

	return &id[choice];
}
