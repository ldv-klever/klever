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

#include <linux/module.h>
#include <ldv/common/test.h>
#include <ldv/verifier/memory.h>

static int __init ldv_init(void)
{
	char *str1 = ldv_xmalloc(4);
	char *str2 = "ldv";

	str1[0] = 'l';
	str1[1] = 'd';
	str1[2] = 'v';
	str1[3] = 0;

	if (strlen(str1) != 3)
		ldv_unexpected_error();

	if (strlen(str2) != 3)
		ldv_unexpected_error();

	ldv_free(str1);

	return 0;
}

module_init(ldv_init);
