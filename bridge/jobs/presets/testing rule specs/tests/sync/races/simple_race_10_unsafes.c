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
int global1 = 0;
int global2 = 0;
int global3 = 0;
int global4 = 0;
int global5 = 0;
int global6 = 0;
int global7 = 0;
int global8 = 0;
int global9 = 0;

void f(void* arg) {
	gvar = 1;
	global1 = 1;
	global2 = 1;
	global3 = 1;
	global4 = 1;
	global5 = 1;
	global6 = 1;
	global7 = 1;
	global8 = 1;
	global9 = 1;
}

void g(void* arg) {
	int b;

	mutex_lock(&my_mutex);
	b = gvar;
	b = global1;
	b = global2;
	b = global3;
	b = global4;
	b = global5;
	b = global6;
	b = global7;
	b = global8;
	b = global9;
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
