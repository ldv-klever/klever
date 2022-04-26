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
#include <scsi/scsi_host.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int flip_a_coin;
struct device *dev;
struct Scsi_Host *host;

static int ldv_reset(struct scsi_cmnd *cmd){
	ldv_invoke_callback();
	return 0;
}

static struct scsi_host_template ldv_template = {
	.eh_bus_reset_handler   = ldv_reset,
};

static int __init ldv_init(void)
{
	int ret = ldv_undef_int();
	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		host = scsi_host_alloc(&ldv_template, sizeof(void *));
		if (host) {
			ldv_register();
			ret = scsi_add_host(host, dev);
			if (ret)
				ldv_deregister();
			return ret;
		}
		else
			return -ENOMEM;
	}
	return ret;
}

static void __exit ldv_exit(void)
{
	if (flip_a_coin) {
		scsi_unregister(host);
		ldv_deregister();
	}
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
