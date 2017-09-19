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

int global = 0;

int g(void) {
  return 0;
}

void* f(void) {
    void *res;
    g();
    global = 0;
    return res;
}

int h(void* arg) {
    int tmp = 0;
    
    f();
    
    g();
    
    f();
}

static int __init init(void)
{
	pthread_t thread1, thread2;

	pthread_create(&thread1, 0, &h, 0);
	mutex_lock(&my_mutex);
	global = 1;
	mutex_unlock(&my_mutex);
	return 0;
}

module_init(init);
