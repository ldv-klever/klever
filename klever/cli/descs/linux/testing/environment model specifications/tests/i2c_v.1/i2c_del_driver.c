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
#include <linux/i2c.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int ldv_probe(struct i2c_client *client, const struct i2c_device_id *id)
{
	ldv_invoke_callback();
	ldv_store_resource1(client);
	return 0;
}

int ldv_remove(struct i2c_client *client)
{
	ldv_invoke_callback();
	ldv_check_resource1(client, 1);
	return 0;
}

struct i2c_driver ldv_driver = {
	.probe = ldv_probe,
	.remove = ldv_remove
};

static int __init ldv_init(void)
{

    int flip_a_coin;
	int ret = ldv_undef_int();
	flip_a_coin = ldv_undef_int();
	if (flip_a_coin) {
		ldv_register();
		ret = i2c_register_driver(THIS_MODULE, & ldv_driver);
		if (!ret) {
			i2c_del_driver(& ldv_driver);
		}
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