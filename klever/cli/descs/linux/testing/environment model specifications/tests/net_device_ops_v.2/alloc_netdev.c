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
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

struct net_device *dev;
struct mutex *ldv_envgen;
int flip_a_coin;
unsigned char name_assign_type;

static netdev_tx_t ldv_xmit(struct sk_buff *skb, struct net_device *dev)
{
	ldv_invoke_callback();
	ldv_check_resource1(dev, 0);
	return 0;
}

static int ldv_open(struct net_device *dev)
{
	ldv_invoke_callback();
	ldv_check_resource1(dev, 0);
	return 0;
}

static int ldv_close(struct net_device *dev)
{
	ldv_invoke_callback();
	ldv_check_resource1(dev, 0);
	return 0;
}

static void ldv_setup(struct net_device *dev)
{
	ldv_store_resource1(dev);
}

static const struct net_device_ops ldv_ops = {
	.ndo_open	= ldv_open,
	.ndo_stop	= ldv_close,
	.ndo_start_xmit = ldv_xmit,
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();
	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		dev = alloc_netdev(sizeof(struct net_device_ops), "ldv_dev", name_assign_type, & ldv_setup);
		if (dev) {
			dev->netdev_ops = &ldv_ops;
			ldv_register();
			ret = register_netdev(dev);
			if (ret)
				ldv_deregister();
		}
		else
			return -ENOMEM;
	}
	return ret;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		unregister_netdev(dev);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
