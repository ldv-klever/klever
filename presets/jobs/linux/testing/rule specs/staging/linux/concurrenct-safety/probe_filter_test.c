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

/* This test checks the work of ProbeFilter. */
#include <linux/module.h>
#include <verifier/nondet.h>
#include <verifier/thread.h>

static int _ldv_global_var;

static void *ldv_probe(void *arg)
{
	_ldv_global_var = 2;
	return NULL;
}

static int __init init(void)
{
	pthread_t thread;
	pthread_attr_t const *attr = ldv_undef_ptr();
	void *arg = ldv_undef_ptr();

	pthread_create(&thread, attr, &ldv_probe, arg);
	_ldv_global_var = 1;

	return 0;
}

module_init(init);
