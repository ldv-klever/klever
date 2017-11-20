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

// The test checks the work path iterator
 
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(my_mutex);

int global; 
int global2; 

void h(int a) 
{
    //access to global is false
    if (a) {
	  global = 1;
    }
}

void l(int a) 
{
    //The first call
    h(1);
}

int f(int a) 
{
    //the second call
    h(a);
    return 0;
}

int k(int a) {
    //one more function call
    h(a);
    return 0;
}

int g(void) {
	int p = 0;
    f(p);
    mutex_lock(&my_mutex);
    global = 2;
    mutex_unlock(&my_mutex);
    l(p);
    k(p);
}

int ldv_main(void* arg) {
	g();
    return 0;
}

static int __init init(void)
{
	pthread_t thread2;

	pthread_create(&thread2, 0, ldv_main, 0);
    ldv_main(0);
	return 0;
}

module_init(init);
