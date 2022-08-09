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
#include <linux/dm-dirty-log.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

static int ldv_ctr(struct dm_dirty_log *log, struct dm_target *ti, unsigned argc, char **argv)
{
	ldv_invoke_reached();
	ldv_store_resource1(log);
	return ldv_undef_int();
}

static void ldv_dtr(struct dm_dirty_log *log)
{
	ldv_invoke_reached();
	ldv_check_resource1(log);
}

static struct dm_dirty_log_type ldv_type = {
	.name = "ldv",
	.module = THIS_MODULE,
	.ctr = ldv_ctr,
	.dtr = ldv_dtr
};

static int __init ldv_init(void)
{
	ldv_invoke_test();
	return dm_dirty_log_type_register(&ldv_type);
}

static void __exit ldv_exit(void)
{
	dm_dirty_log_type_unregister(&ldv_type);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
