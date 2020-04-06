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
#include "func.h"

static int __init ldv_init(void)
{
	struct ldv_struct var = {ldv_func1, ldv_func2};

	if (var.field1(-10) == -10 &&
	    var.field1(-5) == -5 &&
	    var.field1(-2) == -2 &&
	    var.field1(-1) == -1 &&
	    !var.field1(0) &&
	    var.field1(1) == 1 &&
	    var.field1(2) == 2 &&
	    var.field1(5) == 5 &&
	    var.field1(10) == 10 &&
	    var.field2(-10) == 10 &&
	    var.field2(-5) == 5 &&
	    var.field2(-2) == 2 &&
	    var.field2(-1) == 1 &&
	    !var.field2(0) &&
	    var.field2(1) == -1 &&
	    var.field2(2) == -2 &&
	    var.field2(5) == -5 &&
	    var.field2(10) == -10)
		ldv_expected_error();

	return 0;
}

module_init(ldv_init);
