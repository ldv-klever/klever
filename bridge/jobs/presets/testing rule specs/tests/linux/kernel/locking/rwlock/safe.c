/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/module.h>
#include <linux/rwlock.h>

static int __init init(void)
{
	rwlock_t rwlock1, rwlock2, rwlock3;
	unsigned long flags;

    rwlock_init(&rwlock1);
    rwlock_init(&rwlock2);
    rwlock_init(&rwlock3);

	read_lock(&rwlock1);
	read_lock(&rwlock1);
	read_unlock(&rwlock1);
	read_unlock(&rwlock1);

	write_lock(&rwlock1);
	write_unlock(&rwlock1);

	read_lock(&rwlock1);
	read_lock_irqsave(&rwlock1, flags);
	write_lock_irq(&rwlock2);
	write_unlock_irq(&rwlock2);
	read_lock_irq(&rwlock2);
	read_lock_bh(&rwlock3);
	write_lock_bh(&rwlock2);
	write_unlock_bh(&rwlock2);
	read_unlock_bh(&rwlock3);
	read_unlock_irq(&rwlock2);
	read_unlock_irqrestore(&rwlock1, flags);
	read_unlock(&rwlock1);

	write_lock_irqsave(&rwlock1, flags);
	write_unlock_irqrestore(&rwlock1, flags);

	if (read_trylock(&rwlock1)) {
		if (write_trylock(&rwlock1)) {
			write_unlock(&rwlock1);
		}
		read_unlock(&rwlock1);
	}

	return 0;
}

module_init(init);
