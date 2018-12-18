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
#include <linux/spinlock.h>

static DEFINE_RWLOCK(ldv_lock1);
static DEFINE_RWLOCK(ldv_lock2);
static DEFINE_RWLOCK(ldv_lock3);

static int __init ldv_init(void)
{
	unsigned long flags;

	write_lock(&ldv_lock1);
	write_unlock(&ldv_lock1);

	read_lock(&ldv_lock1);
	read_lock_irqsave(&ldv_lock1, flags);

	write_lock_irq(&ldv_lock2);
	write_unlock_irq(&ldv_lock2);

	read_lock_irq(&ldv_lock2);
	read_lock_bh(&ldv_lock3);

	write_lock_bh(&ldv_lock2);
	write_unlock_bh(&ldv_lock2);

	read_unlock_bh(&ldv_lock3);
	read_unlock_irq(&ldv_lock2);
	read_unlock_irqrestore(&ldv_lock1, flags);
	read_unlock(&ldv_lock1);

	write_lock_irqsave(&ldv_lock3, flags);
	write_unlock_irqrestore(&ldv_lock3, flags);

	if (read_trylock(&ldv_lock1)) {
		if (write_trylock(&ldv_lock1))
			write_unlock(&ldv_lock1);

		read_unlock(&ldv_lock1);
	}

	return 0;
}

module_init(ldv_init);
