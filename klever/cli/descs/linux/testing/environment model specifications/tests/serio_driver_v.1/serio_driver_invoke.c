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
#include <linux/serio.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

static int ldv_connect(struct serio *serio, struct serio_driver *drv)
{
	ldv_invoke_reached();
	return 0;
}

static void ldv_disconnect(struct serio *serio)
{
	ldv_invoke_reached();
}

static struct serio_driver ldv_drv = {
	.driver		= {
		.name	= "ldv",
	},
	.connect	= ldv_connect,
	.disconnect	= ldv_disconnect,
};

static int __init ldv_init(void)
{
	ldv_invoke_test();
	return serio_register_driver(&ldv_drv);
}

static void __exit ldv_exit(void)
{
	serio_unregister_driver(&ldv_drv);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
