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
#include <ldv/test.h>
#include "structs.h"

static int __init ldv_init(void)
{
	struct ldv_struct2 *var1;
	int var2 = ldv_undef_int(), var3 = ldv_undef_int(), *var4;

	var1 = ldv_xmalloc(sizeof(*var1) + sizeof(int));

	var1->field1 = var2;
	var4 = (int *)var1->field2;
	*var4 = var3;

	if (var1->field1 != var2)
		ldv_unexpected_error();

	if (*(int *)(var1->field2) != var3)
		ldv_unexpected_error();

	ldv_free(var1);

	return 0;
}

module_init(ldv_init);
