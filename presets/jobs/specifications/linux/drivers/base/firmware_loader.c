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
#include <linux/firmware.h>
#include <verifier/common.h>
#include <verifier/memory.h>
#include <verifier/nondet.h>

int ldv_request_firmware(const struct firmware **fw)
{
	struct firmware *_fw;
	int retval;
  
	retval = ldv_undef_int_nonpositive();

	if (!retval)
    {
		_fw = ldv_xzalloc(sizeof(**fw));
		_fw->data = ldv_malloc_unknown_size();
		ldv_assume(_fw->data);
		*fw = _fw;
    }

	return retval;
}

void ldv_release_firmware(const struct firmware *fw)
{
	if (fw)
    {
		ldv_free(fw->data);
		ldv_free(fw);
    }
}
