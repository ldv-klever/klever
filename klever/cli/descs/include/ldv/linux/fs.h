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

#ifndef __LDV_LINUX_FS_H
#define __LDV_LINUX_FS_H

#include <linux/fs.h>

/* Internal parameter that defines the max number of inodes in the model */
#define MAX_INODES 3

/* Simple model for the inodes tree */
extern unsigned long ldv_created_cnt;
extern struct inode *ldv_inodes[MAX_INODES];

/* VFS functions */
struct inode *ldv_alloc_inode(struct super_block *);
void ldv_inode_init_once(struct inode *);
void ldv_clear_inode(struct inode *);
struct inode *ldv_iget_locked(struct super_block *, unsigned long);
void ldv_iput(struct inode *);

/* Aux functions */
struct inode *ldv_get_root_inode(void);
void ldv_init_list_head(struct list_head *list);

#endif /* __LDV_LINUX_FS_H */
