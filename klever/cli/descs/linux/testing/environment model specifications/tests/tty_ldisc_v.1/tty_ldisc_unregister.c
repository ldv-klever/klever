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
#include <linux/tty_ldisc.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/common.h>

int disc;

int ldv_open(struct tty_struct * tty)
{
	int res;

	ldv_invoke_callback();
	res = ldv_undef_int();
	if (!res) {
		ldv_probe_up();
		ldv_store_resource1(tty);
	}
	return res;
}

void ldv_close(struct tty_struct * tty)
{
	ldv_release_down();
	ldv_invoke_callback();
	ldv_check_resource1(tty, 0);
}

static struct tty_ldisc_ops ldv_tty_ops = {
	.open = ldv_open,
	.close = ldv_close
};

static int __init ldv_init(void)
{
	int res = ldv_undef_int();
	disc = ldv_undef_int();
	ldv_register();
	res = tty_register_ldisc(disc, & ldv_tty_ops);
	if (!res) {
		res = tty_unregister_ldisc(disc);
		ldv_assume(!res);
	}
	ldv_deregister();
	return res;
}

static void __exit ldv_exit(void)
{
	/* Nothing */
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
