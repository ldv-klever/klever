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

struct tty_driver *driver;
struct device *device;
unsigned int lines;
unsigned indx;

int ldv_open(struct tty_struct * tty, struct file * filp)
{
	ldv_invoke_reached();
	return 0;
}

void ldv_close(struct tty_struct * tty, struct file * filp)
{
	ldv_invoke_reached();
}

static struct tty_operations ldv_tty_ops = {
	.open = ldv_open,
	.close = ldv_close
};

static int __init ldv_init(void)
{
	int res = 0;

	ldv_invoke_test();
	driver = tty_alloc_driver(lines, TTY_DRIVER_REAL_RAW);
	if (!IS_ERR(driver)) {
		tty_set_operations(driver, &ldv_tty_ops);
		res = tty_register_driver(driver);
		if (res)
			tty_driver_kref_put(driver);
	} else
		res = PTR_ERR(driver);

	return res;
}

static void __exit ldv_exit(void)
{
	tty_unregister_driver(driver);
	tty_driver_kref_put(driver);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
