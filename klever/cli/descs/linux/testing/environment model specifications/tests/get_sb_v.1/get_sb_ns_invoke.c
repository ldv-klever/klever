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
#include <linux/fs.h>
#include <linux/mount.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

struct file_system_type fs_type;
struct vfsmount mnt;
int flags;

int fill_super(struct super_block *sb, void *a, int b)
{
	ldv_invoke_reached();
	return 0;
}

static int __init ldv_init(void)
{
	ldv_invoke_test();
	return get_sb_ns(& fs_type, flags, NULL, & fill_super, & mnt);
}

static void __exit ldv_exit(void)
{
	 /* Nothing to do */
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
