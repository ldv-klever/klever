/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
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
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */
 
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/thread.h>

struct device;
struct mutex;

struct A {
	int a;
	int b;
};

struct my_data {
	struct mutex lock;
	struct device dev;
	struct A shared;
};

pthread_t *thread;

void* my_callback(void *arg) {
	struct device *dev = (struct device*)arg;
	struct my_data *data;
	data = ({ const typeof( ((struct my_data *)0)->dev ) *__mptr = (dev); (struct my_data *)( (char *)__mptr - ((unsigned long) &((struct my_data *)0)->dev) );});

	mutex_lock (&data->lock);
	data->shared.a = 1;
	data->shared.b = data->shared.b + 1;
	mutex_unlock (&data->lock);
	return 0;
}

int my_drv_probe(struct my_data *data) {
	struct device *d = &data->dev;
	int res = ldv_undef_int();

	data->shared.a = 0;
	data->shared.b = 0;

	if(res)
		goto exit;

	pthread_create_N(&thread, 0, &my_callback, (void *)d);

	data->shared.a = 3;
	data->shared.b = 3;
	return 0;

exit:
	return -1;
}

void my_drv_disconnect(struct my_data *data) {
	pthread_join_N(&thread, &my_callback);
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
