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
	if (-10 * -10 == 100 &&
	    -10 * -5 == 50 &&
	    -10 * -2 == 20 &&
	    -10 * -1 == 10 &&
	    -10 * 0 == 0 &&
	    -10 * 1 == -10 &&
	    -10 * 2 == -20 &&
	    -10 * 5 == -50 &&
	    -10 * 10 == -100 &&
	    -5 * -10 == 50 &&
	    -5 * -5 == 25 &&
	    -5 * -2 == 10 &&
	    -5 * -1 == 5 &&
	    -5 * 0 == 0 &&
	    -5 * 1 == -5 &&
	    -5 * 2 == -10 &&
	    -5 * 5 == -25 &&
	    -5 * 10 == -50 &&
	    -2 * -10 == 20 &&
	    -2 * -5 == 10 &&
	    -2 * -2 == 4 &&
	    -2 * -1 == 2 &&
	    -2 * 0 == 0 &&
	    -2 * 1 == -2 &&
	    -2 * 2 == -4 &&
	    -2 * 5 == -10 &&
	    -2 * 10 == -20 &&
	    -1 * -10 == 10 &&
	    -1 * -5 == 5 &&
	    -1 * -2 == 2 &&
	    -1 * -1 == 1 &&
	    -1 * 0 == 0 &&
	    -1 * 1 == -1 &&
	    -1 * 2 == -2 &&
	    -1 * 5 == -5 &&
	    -1 * 10 == -10 &&
	    0 * -10 == 0 &&
	    0 * -5 == 0 &&
	    0 * -2 == 0 &&
	    0 * -1 == 0 &&
	    0 * 0 == 0 &&
	    0 * 1 == 0 &&
	    0 * 2 == 0 &&
	    0 * 5 == 0 &&
	    0 * 10 == 0 &&
	    1 * -10 == -10 &&
	    1 * -5 == -5 &&
	    1 * -2 == -2 &&
	    1 * -1 == -1 &&
	    1 * 0 == 0 &&
	    1 * 1 == 1 &&
	    1 * 2 == 2 &&
	    1 * 5 == 5 &&
	    1 * 10 == 10 &&
	    2 * -10 == -20 &&
	    2 * -5 == -10 &&
	    2 * -2 == -4 &&
	    2 * -1 == -2 &&
	    2 * 0 == 0 &&
	    2 * 1 == 2 &&
	    2 * 2 == 4 &&
	    2 * 5 == 10 &&
	    2 * 10 == 20 &&
	    5 * -10 == -50 &&
	    5 * -5 == -25 &&
	    5 * -2 == -10 &&
	    5 * -1 == -5 &&
	    5 * 0 == 0 &&
	    5 * 1 == 5 &&
	    5 * 2 == 10 &&
	    5 * 5 == 25 &&
	    5 * 10 == 50 &&
	    10 * -10 == -100 &&
	    10 * -5 == -50 &&
	    10 * -2 == -20 &&
	    10 * -1 == -10 &&
	    10 * 0 == 0 &&
	    10 * 1 == 10 &&
	    10 * 2 == 20 &&
	    10 * 5 == 50 &&
	    10 * 10 == 100)
		ldv_expected_error();

	return 0;
}

module_init(ldv_init);
