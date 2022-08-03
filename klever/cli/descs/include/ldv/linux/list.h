/*
 * Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
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

#ifndef __LDV_LINUX_LIST_H
#define __LDV_LINUX_LIST_H

#include <linux/types.h>

extern void ldv_init_list_head(struct list_head *list);
extern int ldv_list_empty(const struct list_head *head);
extern void ldv_list_add(struct list_head *new, struct list_head *prev, struct list_head *next);
extern void ldv_list_del_entry(struct list_head *prev, struct list_head *next);
extern void ldv_list_del(struct list_head *entry);

#endif /* __LDV_LINUX_LIST_H */
