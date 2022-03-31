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
#include <linux/usb.h>
#include <linux/netdevice.h>
#include <ldv/common/test.h>
#include <ldv/linux/common.h>

static bool ldv_is_initialized = false;
static bool ldv_is_failed_usb_register_driver = false;
static bool ldv_is_failed_register_netdev = false;

void ldv_initialize(void)
{
	ldv_is_initialized = true;
}

static int ldv_usb_probe(struct usb_interface *interface,
                         const struct usb_device_id *id)
{
	return ldv_undef_int_positive();
}

static void ldv_usb_disconnect(struct usb_interface *interface)
{
	/*
	 * This shouldn't be reachable if ldv_post_probe() filters out positive
	 * integers. */
	ldv_unexpected_error();
}

static struct usb_driver ldv_usb_driver = {
	.probe      = ldv_usb_probe,
	.disconnect = ldv_usb_disconnect
};

static int __init ldv_init(void)
{
	int var = ldv_undef_int();
	struct net_device *dev = ldv_undef_ptr();

	if (ldv_in_interrupt_context())
		ldv_unexpected_error();

	ldv_switch_to_interrupt_context();

	if (!ldv_in_interrupt_context())
		ldv_unexpected_error();

	ldv_switch_to_process_context();

	if (ldv_in_interrupt_context())
		ldv_unexpected_error();

	if (!ldv_is_initialized)
		ldv_unexpected_error();

	if (ldv_post_init(var) > 0)
		ldv_unexpected_error();

	if (ldv_post_probe(var) > 0)
		ldv_unexpected_error();

	if (ldv_filter_err_code(var) > 0)
		ldv_unexpected_error();

	if (usb_register(&ldv_usb_driver)) {
		if (!ldv_is_failed_usb_register_driver)
			ldv_unexpected_error();

		return ldv_undef_int_negative();
	}

	usb_deregister(&ldv_usb_driver);

	if (register_netdev(dev)) {
		if (!ldv_is_failed_register_netdev)
			ldv_unexpected_error();

		return ldv_undef_int_negative();
	}

	unregister_netdev(dev);

	/*
	 * We don't test ldv_add_disk() and ldv_remove_disk() since it is unclear
	 * for what they are intended for.
	 */

	return ldv_undef_int_positive();
}

void ldv_failed_usb_register_driver(void)
{
	ldv_is_failed_usb_register_driver = true;
}

void ldv_failed_register_netdev(void)
{
	ldv_is_failed_register_netdev = true;
}

static void __exit ldv_exit(void)
{
	/*
	 * This shouldn't be reachable if ldv_post_init() filters out positive
	 * integers. */
	ldv_unexpected_error();
}

module_init(ldv_init);

MODULE_LICENSE("GPL");
module_exit(ldv_exit);

void ldv_check_final_state(void)
{
	/* We can't check anything after this function. */
}
