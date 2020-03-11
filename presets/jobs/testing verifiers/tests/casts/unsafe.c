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
	if ((unsigned int)-10 == UINT_MAX - 9 &&
	    (int)(UINT_MAX - 9) == -10  &&
	    (unsigned int)-5 == UINT_MAX - 4 &&
	    (int)(UINT_MAX - 4) == -5  &&
	    (unsigned int)-2 == UINT_MAX - 1 &&
	    (int)(UINT_MAX - 1) == -2  &&
	    (unsigned int)-1 == UINT_MAX &&
	    (int)(UINT_MAX) == -1  &&
	    (unsigned int)-0 == 0 &&
	    (int)0 == -0  &&
	    (unsigned int)1 == 1 &&
	    (int)1 == 1  &&
	    (unsigned int)2 == 2 &&
	    (int)2 == 2  &&
	    (unsigned int)5 == 5 &&
	    (int)5 == 5  &&
	    (unsigned int)10 == 10 &&
	    (int)10 == 10 )
		ldv_expected_error();

	return 0;
}

module_init(ldv_init);
