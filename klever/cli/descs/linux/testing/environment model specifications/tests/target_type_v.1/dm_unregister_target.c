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
#include <linux/device-mapper.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

static int ldv_ctr(struct dm_target *ti, unsigned int argc, char **argv)
{
	ldv_invoke_callback();
	ldv_store_resource1(ti);
	return 0;
}

static void ldv_dtr(struct dm_target *ti)
{
	ldv_invoke_callback();
	ldv_check_resource1(ti, 0);
}

static struct target_type ldv_target = {
	.name		= "ldv",
	.module	  = THIS_MODULE,
	.ctr		 = ldv_ctr,
	.dtr		 = ldv_dtr,
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();
	int flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		ldv_register();
		ret = dm_register_target(&ldv_target);
		if (!ret) {
			dm_unregister_target(&ldv_target);
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
