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
#include <linux/device.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int flip_a_coin;

static int ldv_add_dev(struct device *dev, struct class_interface *intf)
{
	ldv_invoke_callback();
	ldv_store_resource1(dev);
	ldv_store_resource2(intf);
	return 0;
}

static void ldv_remove_dev(struct device *dev, struct class_interface *intf)
{
	ldv_invoke_callback();
	ldv_check_resource1(dev, 1);
	ldv_check_resource2(intf, 1);
}

static struct class_interface ldv_driver = {
	.add_dev = ldv_add_dev,
	.remove_dev = ldv_remove_dev,
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();
	flip_a_coin = ldv_undef_int();

	if (flip_a_coin) {
		ldv_register();
		ret = class_interface_register(&ldv_driver);
		if (ret)
			ldv_deregister();
	}
	return ret;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		class_interface_unregister(&ldv_driver);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
