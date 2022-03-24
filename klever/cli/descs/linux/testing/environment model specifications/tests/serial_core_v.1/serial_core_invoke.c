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

struct uart_driver *driver;
struct uart_port *port;

int ldv_startup(struct uart_port *port)
{
	ldv_invoke_reached();
	return 0;
}

void ldv_shutdown(struct uart_port *port)
{
	ldv_invoke_reached();
}

static struct uart_ops ldv_uart_ops = {
	.shutdown = ldv_shutdown,
	.startup = ldv_startup
};

static int __init ldv_init(void)
{
	ldv_invoke_test();
	port->ops = &ldv_uart_ops;
	return uart_add_one_port(driver, port);
}

static void __exit ldv_exit(void)
{
	uart_remove_one_port(driver, port);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
