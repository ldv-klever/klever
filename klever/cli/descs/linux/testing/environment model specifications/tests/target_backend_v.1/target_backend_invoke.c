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
#include <target/target_core_base.h>
#include <target/target_core_backend.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

struct se_device * ldv_alloc_device(struct se_hba *hba, const char *name)
{
	struct se_device *res;
	ldv_invoke_callback();
	res = ldv_undef_ptr();
	ldv_invoke_reached();
	ldv_store_resource1(res);
	return res;
}

static void ldv_free_device(struct se_device *device)
{
	ldv_invoke_reached();
	ldv_check_resource1(device, 1);
}

static struct target_backend_ops ldv_driver = {
	.alloc_device = ldv_alloc_device,
	.free_device = ldv_free_device,
};

static int __init ldv_init(void)
{
	ldv_invoke_test();
	return transport_backend_register(&ldv_driver);
}

static void __exit ldv_exit(void)
{
	target_backend_unregister(&ldv_driver);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
