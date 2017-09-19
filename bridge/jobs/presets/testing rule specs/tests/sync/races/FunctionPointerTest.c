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

/* The test should check processing of function pointers with different declarations */

#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(my_mutex);
int global = 0;

struct F {
  int (*a)(void);
  int (*b)(void);
  int (*c)(int d);
} *var;

int hook(void) {
	int b = 0;
	mutex_lock(&my_mutex);
	global = b++;
	mutex_unlock(&my_mutex);
	return b;
}

int hook2(int a) {
	int b = a + 1;
	global = b++;
	return b;
}

int func(int a) {
  int t = 0;
  var->a();
  var->b();
  var->c(t);
  return 0;
}

void locker(void *arg) {
  mutex_lock(&my_mutex);
  var->a = &hook;
  var->b = &hook;
  var->c = &hook2;  
  mutex_unlock(&my_mutex);
  return 0;
}



static int __init init(void)
{
	pthread_t thread2;

	pthread_create(&thread2, 0, &locker, 0);
	func(0);
	return 0;
}

module_init(init);

