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

/* The main aim of this test is to check handling of variable links. */
#include <linux/module.h>
#include <linux/mutex.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/thread.h>

extern int *ldv_list_get_first(int *arg);
void* calloc( size_t number, size_t size );

static DEFINE_MUTEX(ldv_lock);
static DEFINE_MUTEX(ldv_lock2);
static DEFINE_MUTEX(ldv_lock3);
static struct ldv_struct {
	int a;
	int b;
} *_ldv_var;
static int t, p;

/* Check disjoint sets. */
static int ldv_func(int a)
{
	int *c = &t;

	mutex_lock(&ldv_lock);
	*c = 2;
	mutex_lock(&ldv_lock2);
	*c = 4;
	mutex_unlock(&ldv_lock);
	*c = 3;
	mutex_unlock(&ldv_lock2);

	return 0;
}

static void *ldv_main(void *arg)
{
	int q = 1;
	int *temp = calloc(1, sizeof(int));
	int *temp2;
	
	ldv_func(0);
	
	/* Check links. */
	q = *temp;
	if (q == 1) {
		mutex_lock(&ldv_lock);
		temp = ldv_list_get_first(&(_ldv_var->a));
		mutex_unlock(&ldv_lock);
	}

	temp2 = ldv_list_get_first(temp);
	temp2 = ldv_list_get_first(temp2);
	/* Important: there two links possible: temp and s->a. */
	*temp2 = 1;
	
	/* Check parameter locks. */
	mutex_lock(&ldv_lock3);
	p = 1;
	mutex_unlock(&ldv_lock3);
	p = 2;

	return 0;
}

static int __init init(void)
{
	pthread_t thread1, thread2;
	pthread_attr_t const *attr = ldv_undef_ptr();
	void *arg1 = ldv_undef_ptr(), *arg2 = ldv_undef_ptr();

	pthread_create(&thread1, attr, &ldv_main, arg1);
	pthread_create(&thread2, attr, &ldv_main, arg2);

	return 0;
}

module_init(init);
