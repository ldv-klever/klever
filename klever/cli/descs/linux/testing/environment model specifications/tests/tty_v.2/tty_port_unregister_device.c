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
#include <linux/tty.h>
#include <linux/tty_driver.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int flip_a_coin;
struct tty_driver *driver;
struct tty_port port;
struct device *device;

static int ldv_activate(struct tty_port *tport, struct tty_struct *tty)
{
	ldv_invoke_callback();
	ldv_check_resource1(tport, 0);
	return 0;
}

static void ldv_shutdown(struct tty_port *tport)
{
	ldv_invoke_callback();
	ldv_check_resource1(tport, 0);
}

static const struct tty_port_operations ldv_tty_port_ops = {
	.activate = ldv_activate,
	.shutdown = ldv_shutdown,
};

static int __init ldv_init(void)
{
	struct device *dev;

	ldv_invoke_test();
	tty_port_init(&port);
	port.ops = &ldv_tty_port_ops;

	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		ldv_register();
		ldv_store_resource1(&port);
		dev = tty_port_register_device(&port, driver, ldv_undef_int(), device);
		if (!IS_ERR(dev))
			tty_port_destroy(&port);
		ldv_deregister();
	}

	return 0;
}

static void __exit ldv_exit(void)
{
	/* Do nothing */
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
