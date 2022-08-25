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
#include "../drivers/md/md.h"
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int flip_a_coin;

static int ldv_run(struct mddev *mddev)
{
	int res;

	ldv_invoke_callback();
	res = ldv_undef_int();
	if (!res) {
		ldv_probe_up();
		ldv_store_resource1(mddev);
	}
	return res;
}

static void md_free(struct mddev *mddev, void *priv)
{
	ldv_release_down();
	ldv_invoke_callback();
	ldv_check_resource1(mddev, 0);
}

static struct md_personality ldv_personality =
{
	.name		= "ldv",
	.run		= ldv_run,
	.free		= md_free,
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();
	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		ldv_register();
		ret = register_md_personality(&ldv_personality);
		if (ret)
			ldv_deregister();
	}
	return ret;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		unregister_md_personality(&ldv_personality);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
