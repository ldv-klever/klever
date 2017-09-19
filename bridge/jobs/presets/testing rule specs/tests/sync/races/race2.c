/*
 * Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
 * Institute for System Programming of the Russian Academy of Sciences
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
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(my_mutex);

int gvar = 0;

void f(void* arg) {
	gvar = 1;
}

void g(void* arg) {
	int b;

	mutex_lock(&my_mutex);
	b = gvar;
	mutex_unlock(&my_mutex);
}

static int __init init(void)
{
	pthread_t thread1, thread2;

	pthread_create(&thread1, 0, &f, 0);
	pthread_create(&thread2, 0, &g, 0);

	return 0;
}

module_init(init);
