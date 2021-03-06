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

#include <linux/module.h>
#include <linux/mutex.h>
#include <linux/rcupdate.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/thread.h>

void* calloc( size_t number, size_t size );
void free(void *mem);

static char * gp;

void *reader(void * arg)
{
	char *a;
	char b;

	rcu_read_lock();
	a = rcu_dereference(gp);
	b = *a;
	rcu_read_unlock();

	return NULL;
}

void *writer(void * arg)
{
	char * pWriter = calloc(3,sizeof(int));
	char * ptr = gp;

	pWriter[0] = 'r';
	pWriter[1] = 'c';
	pWriter[2] = 'u';

	rcu_assign_pointer(gp, pWriter);
	synchronize_rcu();
	free(ptr);

	return NULL;
}

static int __init ldv_init(void)
{
	pthread_attr_t const *attr = ldv_undef_ptr();
	void *arg1 = ldv_undef_ptr(), *arg2 = ldv_undef_ptr();
	pthread_t rd, wr;

	gp = calloc(3,sizeof(int));

	pthread_create(&rd, attr, reader, arg1);
	pthread_create(&wr, attr, writer, arg2);

	return 0;
}

module_init(ldv_init);
