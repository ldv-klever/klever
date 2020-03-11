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

static int __init ldv_init(void)
{
	if (((0 >> 0) == 0) &&
	    ((0 >> 1) == 0) &&
	    ((0 >> 2) == 0) &&
	    ((0 >> 5) == 0) &&
	    ((0 >> 10) == 0) &&
	    ((1 >> 0) == 1) &&
	    ((1 >> 1) == 0) &&
	    ((1 >> 2) == 0) &&
	    ((1 >> 5) == 0) &&
	    ((1 >> 10) == 0) &&
	    ((2 >> 0) == 2) &&
	    ((2 >> 1) == 1) &&
	    ((2 >> 2) == 0) &&
	    ((2 >> 5) == 0) &&
	    ((2 >> 10) == 0) &&
	    ((5 >> 0) == 5) &&
	    ((5 >> 1) == 2) &&
	    ((5 >> 2) == 1) &&
	    ((5 >> 5) == 0) &&
	    ((5 >> 10) == 0) &&
	    ((10 >> 0) == 10) &&
	    ((10 >> 1) == 5) &&
	    ((10 >> 2) == 2) &&
	    ((10 >> 5) == 0) &&
	    ((10 >> 10) == 0))
		ldv_expected_error();

	return 0;
}

module_init(ldv_init);
