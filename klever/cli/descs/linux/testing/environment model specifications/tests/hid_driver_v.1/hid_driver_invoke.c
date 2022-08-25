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
#include <linux/hid.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>


int ldv_probe(struct hid_device *dev, const struct hid_device_id *id)
{
	ldv_invoke_reached();
	ldv_store_resource1(dev);
	return 0;
}

void ldv_remove(struct hid_device *dev)
{
	ldv_invoke_reached();
	ldv_check_resource1(dev, 1);
}

struct hid_driver ldv_driver = {
	.probe = ldv_probe,
	.remove = ldv_remove
};

static int __init ldv_init(void)
{
	ldv_invoke_test();
	return __hid_register_driver(& ldv_driver, THIS_MODULE, KBUILD_MODNAME);
}

static void __exit ldv_exit(void)
{
	hid_unregister_driver(& ldv_driver);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
