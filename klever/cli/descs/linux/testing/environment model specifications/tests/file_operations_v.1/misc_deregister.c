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
#include <linux/miscdevice.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int flip_a_coin;

static int ldv_open(struct inode *inode, struct file *filp)
{
	ldv_invoke_callback();
	ldv_store_resource1(inode);
	ldv_store_resource2(filp);
	return 0;
}

static int ldv_release(struct inode *inode, struct file *filp)
{
	ldv_invoke_callback();
	ldv_check_resource1(inode, 1);
	ldv_check_resource2(filp, 1);
	return 0;
}

static struct file_operations ldv_fops = {
	.open		= ldv_open,
	.release	= ldv_release,
	.owner		= THIS_MODULE,
};

static struct miscdevice ldv_misc = {
	.fops = & ldv_fops
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();
	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		ldv_register();
		ret = misc_register(&ldv_misc);
		if (!ret) {
			misc_deregister(&ldv_misc);
		}
		ldv_deregister();
	}
	return ret;
}

static void __exit ldv_exit(void)
{
	/* pass */
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
