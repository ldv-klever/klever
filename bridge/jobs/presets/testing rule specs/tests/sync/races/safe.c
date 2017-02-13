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

static DEFINE_MUTEX(my_mutex);

int gvar;

struct my_struct {
	int (*func)(void);
	int (*gunc)(void);
};

int f(void) {
	mutex_lock(&my_mutex);
	gvar = 1;
	mutex_unlock(&my_mutex);
	return 0;
}

void g(void) {
	int b;

	mutex_lock(&my_mutex);
	b = gvar;
	mutex_unlock(&my_mutex);
}

struct my_struct my_driver = {
	.func = f,
	.gunc = g
};

static int __init init(void)
{
	return 0;
}

module_init(init);
