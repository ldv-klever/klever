/*
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

/* Test check the reduction of locks */

#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(my_mutex);
static DEFINE_MUTEX(my_mutex2);
static DEFINE_MUTEX(my_mutex3);

int gvar;

int f(void) {
    gvar = 0;
    mutex_lock(&my_mutex);
    mutex_lock(&my_mutex2);
    mutex_lock(&my_mutex3);
	return 0;
}

void ldv_main(void) {
    mutex_lock(&my_mutex);
    mutex_lock(&my_mutex);
	mutex_lock(&my_mutex2);
    //(2,1,0) -> (1,1,0)
	f();
    //(0,2,1) -> (1,2,1)
    //(1,2,1) -> (1,1,1)
	f();
    //(0,2,2) -> (0,3,3)
    mutex_unlock(&my_mutex2);
    mutex_unlock(&my_mutex2);
    mutex_unlock(&my_mutex2);
    //(0,0,3) -> (0,0,1)
    f();
    //(0,1,2) -> (0,1,4)
}

static int __init init(void)
{
	pthread_t thread2;

	pthread_create(&thread2, 0, ldv_main, 0);
    ldv_main();
	return 0;
}

module_init(init);
