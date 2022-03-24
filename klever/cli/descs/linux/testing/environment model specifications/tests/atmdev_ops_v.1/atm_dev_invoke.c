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
#include <linux/atmdev.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

struct atm_dev *ldv_dev;

static void ldv_close(struct atm_vcc *dev)
{
	ldv_invoke_reached();
}


static int ldv_open(struct atm_vcc *vcc)
{
	ldv_invoke_reached();
	return ldv_undef_int();
}

static struct atmdev_ops ldv_ops = {
	.open = & ldv_open,
	.close = & ldv_close
};

static int __init ldv_init(void)
{
	unsigned long *flags = ldv_undef_ptr();
	int ret = ldv_undef_int();

	ldv_invoke_test();
	ldv_dev = atm_dev_register("ldv", &ldv_ops, ldv_undef_int(), flags);
	if (!ldv_dev) {
		ret = ldv_undef_int_negative();
	}
	return ret;
}

static void __exit ldv_exit(void)
{
	atm_dev_deregister(ldv_dev);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
