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

int flip_a_coin;

static int ldv_get_sb(struct file_system_type *fs_type, int flags, const char *dev_name, void *data, struct vfsmount *mnt)
{
	int res;

	ldv_invoke_callback();
	res = ldv_undef_int();
	if (!res)
		ldv_probe_up();

	return res;
}

static void ldv_kill_sb(struct super_block *sb)
{
	ldv_release_down();
	ldv_invoke_callback();
}

static struct file_system_type ldv_fs = {
	.get_sb = ldv_get_sb,
	.kill_sb = ldv_kill_sb,
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();

	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		ldv_register();
		ret = register_filesystem(&ldv_fs);
		if (ret)
			ldv_deregister();
	}

	return ret;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		unregister_filesystem(&ldv_fs);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
