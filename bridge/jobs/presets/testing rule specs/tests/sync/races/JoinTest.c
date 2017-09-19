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

/* The test should check processing of function pointers with different declarations */

#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(my_mutex);
int safe;
int unsafe;

int f(void) {
    safe = 1;
    unsafe = 1;
}

void* control_function(void *arg) {
    f();
}

static int __init init(void)
{
	pthread_t thread2;
	void* status;

	pthread_create(&thread2, 0, &control_function, 0);
    unsafe = 0;
    pthread_join(&thread2, &status);
	return 0;
}

module_init(init);
