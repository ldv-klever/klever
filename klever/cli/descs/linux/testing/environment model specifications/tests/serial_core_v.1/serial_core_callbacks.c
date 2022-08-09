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
#include <linux/serial_core.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int flip_a_coin;
struct uart_driver *driver;
struct uart_port *port;
int res;

int ldv_startup(struct uart_port *port)
{
	ldv_invoke_callback();
	ldv_check_resource1(port);
	res = ldv_undef_int();
	if (!res)
		ldv_probe_up();
	return res;
}

void ldv_shutdown(struct uart_port *port)
{
	if (!res) {
	  ldv_release_down();
	}
	ldv_invoke_callback();
	ldv_check_resource1(port);
}

static struct uart_ops ldv_uart_ops = {
	.shutdown = ldv_shutdown,
	.startup = ldv_startup
};

static int __init ldv_init(void)
{
	int res = ldv_undef_int();
	flip_a_coin = ldv_undef_int();
	if(flip_a_coin) {
		port->ops = &ldv_uart_ops;
		ldv_register();
		ldv_store_resource1(port);
		res = uart_add_one_port(driver, port);
		if (res)
			ldv_deregister();
	}

	return res;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		uart_remove_one_port(driver, port);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
