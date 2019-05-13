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
#include <linux/completion.h>

int __init my_init(void)
{
	struct completion x1, x2;
	DECLARE_COMPLETION_ONSTACK(work);

	init_completion(&x1);
	init_completion(&x2);

	wait_for_completion(&x1);

	init_completion(&x1);
	wait_for_completion(&x1);

	wait_for_completion(&x2);
	wait_for_completion(&work);

	return 0;
}

module_init(my_init);
