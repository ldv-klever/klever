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
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

static struct dentry *ldv_mount(struct file_system_type *fs_type, int flags, const char *dev_name, void *data)
{
	ldv_invoke_reached();
	ldv_check_resource1(fs_type, 0);
	return NULL;
}

static void ldv_kill_sb(struct super_block *sb)
{
	ldv_invoke_reached();
}

static struct file_system_type ldv_fs = {
	.mount = ldv_mount,
	.kill_sb = ldv_kill_sb,
};

static int __init ldv_init(void)
{
	ldv_invoke_test();
	ldv_store_resource1(&ldv_fs);
	return register_filesystem(&ldv_fs);
}

static void __exit ldv_exit(void)
{
	unregister_filesystem(&ldv_fs);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
