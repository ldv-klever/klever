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
extern int my_print(const char * s, int); 
extern int undef_int(void); 

int print(void) {
	if (global % 2 == 0) {
		my_print("global is even: %d", global);
    } else {
		my_print("global is odd: %d", global);
	}
	return 0;
}

int increase(void) {
	mutex_lock(&my_mutex);
	global++;
	mutex_unlock(&my_mutex);
	return 0;
}

void* ldv_main(void* arg) {
	switch(undef_int()) {
		case 0:
			print();
			break;
		
		case 1:
			increase();
			break;
    }
    return 0;
}

static int __init init(void)
{
	pthread_t thread2;

	pthread_create(&thread2, 0, &ldv_main, 0);
	ldv_main(0);
	return 0;
}

module_init(init);
