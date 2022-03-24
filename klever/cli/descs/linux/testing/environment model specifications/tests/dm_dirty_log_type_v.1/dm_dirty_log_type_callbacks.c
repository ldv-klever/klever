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
#include <linux/dm-dirty-log.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int flip_a_coin;

static int ldv_ctr(struct dm_dirty_log *log, struct dm_target *ti, unsigned argc, char **argv)
{
	int res;
	res = ldv_undef_int();

	ldv_invoke_callback();
	if (!res)
		ldv_probe_up();

	return res;
}

static void ldv_dtr(struct dm_dirty_log *log)
{
	ldv_release_down();
	ldv_invoke_callback();
}

static struct dm_dirty_log_type ldv_type = {
	.name = "ldv",
	.module = THIS_MODULE,
	.ctr = ldv_ctr,
	.dtr = ldv_dtr
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();
	
	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		ldv_register();
		ret = dm_dirty_log_type_register(&ldv_type);
		if (ret)
			ldv_deregister();
	}
	return ret;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		dm_dirty_log_type_unregister(&ldv_type);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
