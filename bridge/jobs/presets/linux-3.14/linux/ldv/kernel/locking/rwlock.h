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

#include <linux/spinlock_types.h>

extern void ldv_read_lock(rwlock_t *lock);
extern void ldv_read_unlock(rwlock_t *lock);

extern void ldv_write_lock(rwlock_t *lock);
extern void ldv_write_unlock(rwlock_t *lock);

extern int ldv_read_trylock(rwlock_t *lock);
extern int ldv_write_trylock(rwlock_t *lock);
