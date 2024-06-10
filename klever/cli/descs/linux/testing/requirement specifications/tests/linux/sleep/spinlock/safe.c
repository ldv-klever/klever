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
#include <linux/interrupt.h>
#include <ldv/verifier/nondet.h>
#include <linux/mmiotrace.h>

static DEFINE_SPINLOCK(ldv_lock);

static inline void ldv_sleep(void) {
	void *ec = ldv_undef_ptr();
	mmiotrace_iounmap(ec);
}

static int __init ldv_init(void)
{
	ldv_sleep();

	spin_lock(&ldv_lock);
	spin_unlock(&ldv_lock);

	return 0;
}

module_init(ldv_init);
