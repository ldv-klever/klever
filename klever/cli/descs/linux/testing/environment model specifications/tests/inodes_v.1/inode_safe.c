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

#include <linux/module.h>
#include <linux/fs.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

#include "mkdir-middle-callback.h"


static int ldv_rmdir(struct inode *parent, struct dentry *child)
{
	ldv_invoke_middle_callback();
	return 0;
}

const struct inode_operations ldv_dir_inops = {
	.mkdir			= ldv_mkdir,
	.rmdir			= ldv_rmdir
};

static struct inode *ldv_super_alloc_inode(struct super_block *sb)
{
	return ldv_undef_ptr();
}

static const struct super_operations ldv_sops = {
	.alloc_inode	= ldv_super_alloc_inode
};

static int ldv_fill_super(struct super_block *s, void *data, int silent)
{
	struct inode *inode;
	
	s->s_op = &ldv_sops;
	inode = iget_locked(s, 0);
	if (IS_ERR(inode))
		return -ENOMEM;

	s->s_root = d_make_root(inode);
	if (!s->s_root)
		return -ENOMEM;

	return 0;
}

static struct dentry *ldv_mount(struct file_system_type *fs_type, int flags, const char *dev_name, void *data)
{
	struct dentry *dentry;
	
	ldv_invoke_callback();
	dentry = mount_bdev(fs_type, flags, dev_name, data, ldv_fill_super);
	if (dentry != 0)
		ldv_probe_up();

	return dentry;
}

static void ldv_kill_sb(struct super_block *sb)
{
	ldv_release_down();
	ldv_invoke_callback();
}

static struct file_system_type ldv_fs = {
	.mount = ldv_mount,
	.kill_sb = ldv_kill_sb,
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();

	ldv_register();
	ret = register_filesystem(&ldv_fs);
	if (ret)
		ldv_deregister();

	return ret;
}

static void __exit ldv_exit(void)
{
	unregister_filesystem(&ldv_fs);
	ldv_deregister();
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
