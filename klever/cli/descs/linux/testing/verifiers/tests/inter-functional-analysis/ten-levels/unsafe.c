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
#include "funcs.h"

static int __init ldv_init(void)
{
	if (ldv_func1(1) == 1 &&
	    ldv_func2(2) == -2 &&
	    ldv_func3(3) == 3 &&
	    ldv_func4(4) == -4 &&
	    ldv_func5(5) == 5 &&
	    ldv_func6(6) == -6 &&
	    ldv_func7(7) == 7 &&
	    ldv_func8(8) == -8 &&
	    ldv_func9(9) == 9 &&
	    ldv_func10(10) == -10)
		ldv_expected_error();

	return 0;
}

module_init(ldv_init);
