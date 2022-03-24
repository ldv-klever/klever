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
#include <linux/workqueue.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

static struct delayed_work work;
static struct workqueue_struct *queue;

static void ldv_handler(struct work_struct *work)
{
	ldv_invoke_callback();
}

static int __init ldv_init(void)
{
	ldv_invoke_test();
	queue = create_workqueue("ldv_queue");
	if (!queue)
		return -ENOMEM;
	INIT_DELAYED_WORK(&work, ldv_handler);
	flush_delayed_work(&work);
	return 0;
}

static void __exit ldv_exit(void)
{
	destroy_workqueue(queue);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
