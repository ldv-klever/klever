/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *	http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

// The test checks the work path iterator
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/thread.h>

static DEFINE_MUTEX(ldv_lock);
int pdev;

pthread_t thread;

void* thread1(void *arg) {
	mutex_lock(&ldv_lock);
	pdev = 6;
	mutex_unlock(&ldv_lock);
	return 0;
}

static int __init ldv_init(void) {

	pdev = 1;
	if(ldv_undef_int()) {

		pthread_create(&thread, 0, thread1, ((void *)0));

		pdev = 2;	  // RACE!
		return 0;
	}

	pdev = 3;
	return -1;
}

static void __exit ldv_exit(void) {
	void *status;

	pthread_join(thread, &status);

	pdev = 5;
}

module_init(ldv_init);
module_exit(ldv_exit);
