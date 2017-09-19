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
 
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>

#ifndef offsetof
#define offsetof(TYPE, MEMBER) ((unsigned long) &((TYPE *)0)->MEMBER)
#endif

#ifndef container_of
#define container_of(ptr, type, member) ({                      \
	const typeof( ((type *)0)->member ) *__mptr = (ptr);    \
	(type *)( (char *)__mptr - offsetof(type,member) );})
#endif

int __VERIFIER_nondet_int(void);

pthread_t t1,t2;

struct A {
	int a;
	int b;
};

struct my_data {
	struct mutex lock;
	struct device dev;
	struct A shared;
};

struct device *my_dev;

void *my_callback(void *arg) {
	struct my_data *data;
	data = container_of(my_dev, struct my_data, dev);
	
	mutex_lock (&data->lock);
	data->shared.a = 1;
	data->shared.b = data->shared.b + 1;
	mutex_unlock (&data->lock);
	return 0;
}

int my_drv_probe(struct my_data *data) {
	//init data (single thread)
	//not a race
	data->shared.a = 0;
	data->shared.b = 0;
	
	int res;
	res = __VERIFIER_nondet_int();
	if(res)
		goto exit;

	//share device using global variable
	my_dev = &data->dev;
	
	//register callback
	pthread_create(&t1, 0, my_callback, NULL);
	pthread_create(&t2, 0, my_callback, NULL);
	return 0;

exit:
	return -1;
}

void my_drv_disconnect(struct my_data *data) {
	void *status;
	pthread_join(t1, &status);
	pthread_join(t2, &status);
}

int my_drv_init(void) {
	return 0;
}
 
void my_drv_cleanup(void) {
	return;
}

void* ldv_main(void* arg) {
	int ret = my_drv_init();
	if(ret==0) {
		int probe_ret;
		struct my_data data;
		probe_ret = my_drv_probe(&data);
		if(probe_ret==0) {
			my_drv_disconnect(&data);
		}
		my_drv_cleanup();
		data.shared.a = -1;
		data.shared.b = -1;
	}
	return 0;
}

static int __init init(void)
{
	pthread_t thread2;

	pthread_create(&thread2, 0, ldv_main, 0);
	return 0;
}

module_init(init);
