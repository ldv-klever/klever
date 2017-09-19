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

// The test checks the work of cleanin BAM caches

#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>


int global; 
int global2; 

static DEFINE_MUTEX(my_mutex);

void h(int a) 
{
    //Uninportant function.
	int b = 0;
    b++;
    if (a > b) {
        b++;
    }
}

void l(int a) 
{
    //Uninportant function.
	int b = 0;
    b++;
    if (a > b) {
        b++;
    }
}

int f(int a) 
{
    //Uninportant function, but there were predicates inserted.
	int b = 0;
    b++;
    if (a > b) {
        b++;
    }
	return b;
}

int g(void* arg) {
	int p = 0;
    int b;
    h(p);
	b = f(p);
    l(p);
	mutex_lock(&my_mutex);
    if (b == 0) {
      //false unsafe. f should be cleaned after refinement.  
	  global++;
    }
    //true unsafe
    global2++;    
	mutex_unlock(&my_mutex);
}

static int __init init(void)
{
	pthread_t thread2;

	pthread_create(&thread2, 0, &g, 0);
	global++;
	global2++;
	return 0;
}

module_init(init);
