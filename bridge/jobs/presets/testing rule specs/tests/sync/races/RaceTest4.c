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

int global;
int true_unsafe;
int true_unsafe2;
int true_unsafe3;
int true_unsafe4;

struct A {
	int* a;
};

int f(int a) {
  if (global != 0) {
	mutex_lock(&my_mutex);
	true_unsafe = 1;
	true_unsafe2 = 1;
	mutex_unlock(&my_mutex);
	if (global == 0) {
	 true_unsafe2 = 0;
	}		
  }
  if (((struct A *)23)->a != 0) {
	mutex_lock(&my_mutex);
	true_unsafe3 = 0;
	mutex_unlock(&my_mutex);
	if (((struct A *)23)->a == 0) {		  
	  true_unsafe3 = 0;
	}
  }
  if (a != 0) {
	mutex_lock(&my_mutex);
    true_unsafe4 = 1;
	mutex_unlock(&my_mutex);
  }
  return 0;
} 

int may_main(void) {
  global = 0;
  true_unsafe4 = 0;
  ((struct A *)23)->a = 0;
  f(global);
  true_unsafe = 0;
  return 0;
}

int ldv_main(void* arg) {
	may_main();
}

static int __init init(void)
{
	pthread_t thread2;

	pthread_create(&thread2, 0, &ldv_main, 0);
	ldv_main(0);
	return 0;
}

module_init(init);
