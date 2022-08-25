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
#include <linux/netdevice.h>
#include <linux/ethtool.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

struct net_device dev;

static int set_settings(struct net_device *dev, struct ethtool_cmd *cmd)
{
	ldv_invoke_callback();
	ldv_check_resource1(dev, 0);
	return 0;
}

static struct ethtool_ops ops = {
	.set_settings = set_settings
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();
	int flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		netdev_set_default_ethtool_ops(&dev, &ops);
		ldv_register();
		ldv_store_resource1(&dev);
		ret = register_netdev(&dev);
		if (!ret)
			unregister_netdev(&dev);
		ldv_deregister();
	}
	return ret;
}

static void __exit ldv_exit(void)
{
	/* pass */
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
