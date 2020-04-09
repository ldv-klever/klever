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
	if (-10 + -10 == -20 &&
	    -10 + -5 == -15 &&
	    -10 + -2 == -12 &&
	    -10 + -1 == -11 &&
	    -10 + 0 == -10 &&
	    -10 + 1 == -9 &&
	    -10 + 2 == -8 &&
	    -10 + 5 == -5 &&
	    -10 + 10 == 0 &&
	    -5 + -10 == -15 &&
	    -5 + -5 == -10 &&
	    -5 + -2 == -7 &&
	    -5 + -1 == -6 &&
	    -5 + 0 == -5 &&
	    -5 + 1 == -4 &&
	    -5 + 2 == -3 &&
	    -5 + 5 == 0 &&
	    -5 + 10 == 5 &&
	    -2 + -10 == -12 &&
	    -2 + -5 == -7 &&
	    -2 + -2 == -4 &&
	    -2 + -1 == -3 &&
	    -2 + 0 == -2 &&
	    -2 + 1 == -1 &&
	    -2 + 2 == 0 &&
	    -2 + 5 == 3 &&
	    -2 + 10 == 8 &&
	    -1 + -10 == -11 &&
	    -1 + -5 == -6 &&
	    -1 + -2 == -3 &&
	    -1 + -1 == -2 &&
	    -1 + 0 == -1 &&
	    -1 + 1 == 0 &&
	    -1 + 2 == 1 &&
	    -1 + 5 == 4 &&
	    -1 + 10 == 9 &&
	    0 + -10 == -10 &&
	    0 + -5 == -5 &&
	    0 + -2 == -2 &&
	    0 + -1 == -1 &&
	    0 + 0 == 0 &&
	    0 + 1 == 1 &&
	    0 + 2 == 2 &&
	    0 + 5 == 5 &&
	    0 + 10 == 10 &&
	    1 + -10 == -9 &&
	    1 + -5 == -4 &&
	    1 + -2 == -1 &&
	    1 + -1 == 0 &&
	    1 + 0 == 1 &&
	    1 + 1 == 2 &&
	    1 + 2 == 3 &&
	    1 + 5 == 6 &&
	    1 + 10 == 11 &&
	    2 + -10 == -8 &&
	    2 + -5 == -3 &&
	    2 + -2 == 0 &&
	    2 + -1 == 1 &&
	    2 + 0 == 2 &&
	    2 + 1 == 3 &&
	    2 + 2 == 4 &&
	    2 + 5 == 7 &&
	    2 + 10 == 12 &&
	    5 + -10 == -5 &&
	    5 + -5 == 0 &&
	    5 + -2 == 3 &&
	    5 + -1 == 4 &&
	    5 + 0 == 5 &&
	    5 + 1 == 6 &&
	    5 + 2 == 7 &&
	    5 + 5 == 10 &&
	    5 + 10 == 15 &&
	    10 + -10 == 0 &&
	    10 + -5 == 5 &&
	    10 + -2 == 8 &&
	    10 + -1 == 9 &&
	    10 + 0 == 10 &&
	    10 + 1 == 11 &&
	    10 + 2 == 12 &&
	    10 + 5 == 15 &&
	    10 + 10 == 20)
		ldv_expected_error();

	return 0;
}

module_init(ldv_init);
