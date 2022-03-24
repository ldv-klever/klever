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
#include <linux/device.h>
#include <linux/rtc.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>


struct device *dev;
struct rtc_device *rtc;
int flip_a_coin;

static int ldv_read_time(struct device *dev, struct rtc_time *tm)
{
	ldv_invoke_callback();
	return 0;
}

static const struct rtc_class_ops ldv_ops = {
	.read_time = ldv_read_time,
};

static int __init ldv_init(void)
{
	flip_a_coin = ldv_undef_int();
	dev = ldv_undef_ptr();
	if (flip_a_coin) {
		ldv_register();
		rtc = rtc_device_register("rtc-ldv", dev, &ldv_ops, THIS_MODULE);
		if (IS_ERR(rtc)) {
			ldv_deregister();
			return PTR_ERR(rtc);
		}
	}
	return 0;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		rtc_device_unregister(rtc);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
