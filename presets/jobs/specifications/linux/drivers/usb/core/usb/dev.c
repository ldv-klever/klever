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

#include <ldv/linux/common.h>
#include <ldv/verifier/common.h>
#include <ldv/verifier/map.h>

struct usb_device;

ldv_map LDV_USB_DEV_REF_COUNTS;

struct usb_device *ldv_usb_get_dev(struct usb_device *dev)
{
	/* NOTE Whether USB device is not NULL */
	if (dev) {
		/* NOTE Increment USB device reference counter */
		ldv_map_put(LDV_USB_DEV_REF_COUNTS, dev,
			ldv_map_contains_key(LDV_USB_DEV_REF_COUNTS, dev)
				? ldv_map_get(LDV_USB_DEV_REF_COUNTS, dev) + 1
				: 1);
	}

	/* NOTE USB device */
	return dev;
}

void ldv_usb_put_dev(struct usb_device *dev)
{
	/* NOTE Whether USB device is not NULL */
	if (dev) {
		if (!ldv_map_contains_key(LDV_USB_DEV_REF_COUNTS, dev))
			/* ASSERT USB device reference counter must be incremented */
			ldv_assert();

		if (ldv_map_get(LDV_USB_DEV_REF_COUNTS, dev) <= 0)
			/* ASSERT USB device reference counter must be incremented */
			ldv_assert();

		/* NOTE Decrement USB device reference counter */
		ldv_map_get(LDV_USB_DEV_REF_COUNTS, dev) > 1
			? ldv_map_put(LDV_USB_DEV_REF_COUNTS, dev, ldv_map_get(LDV_USB_DEV_REF_COUNTS, dev) - 1)
			: ldv_map_remove(LDV_USB_DEV_REF_COUNTS, dev);
	}
}

void ldv_check_return_value_probe(int retval)
{
	/* NOTE probe() finished unsuccessfully and returned error code */
	if (retval && !ldv_map_is_empty(LDV_USB_DEV_REF_COUNTS))
		/* ASSERT USB device reference counter should not be increased */
		ldv_assert();
}

void ldv_initialize(void)
{
	/* NOTE All USB device reference counters aren't incremented at the beginning */
	ldv_map_init(LDV_USB_DEV_REF_COUNTS);
}

void ldv_check_final_state(void)
{
	if (!ldv_map_is_empty(LDV_USB_DEV_REF_COUNTS))
		/* ASSERT All incremented USB device reference counters must be decremented at the end */
		ldv_assert();
}
