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

int	ldv_get_fecparam(struct net_device *dev, struct ethtool_fecparam *fecparam)
{
	ldv_invoke_reached();
	ldv_check_resource1(dev);
	return 0;
}

static struct ethtool_ops ops = {
	.get_fecparam = ldv_get_fecparam
};

static int __init ldv_init(void)
{
	ldv_invoke_test();
	ldv_store_resource1(&dev);
	netdev_set_default_ethtool_ops(&dev, &ops);
	return register_netdev(&dev);
}

static void __exit ldv_exit(void)
{
	unregister_netdev(&dev);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
