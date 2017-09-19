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

/* The main aim of this test is to check handling of variable links */
 
#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(my_mutex);
static DEFINE_MUTEX(my_mutex2);
static DEFINE_MUTEX(my_mutex3);

struct testStruct {
  int a;
  int b;
} *s;

int t, p;

struct testStruct *s1;

int* ldv_list_get_first(int* arg);

//Check disjoint sets
int f(int a)
{
  int *c = &t;
  mutex_lock(&my_mutex);
  *c = 2;
  mutex_lock(&my_mutex2);
  *c = 4;
  mutex_unlock(&my_mutex);
  *c = 3;
  mutex_lock(&my_mutex2);
  return 0;
}

void* ldv_main(void* arg) 
{
  int a;
  int q = 1;
  int* temp;
  int* temp2;
  
  f(0);
  
  //Check links
  q = *temp;
  if (q == 1) {
    mutex_lock(&my_mutex);
    temp = ldv_list_get_first(&(s->a));
    mutex_unlock(&my_mutex);
  } 
  temp2 = ldv_list_get_first(temp);
  temp2 = ldv_list_get_first(temp2);
  //Important: there two links possible: temp and s->a
  *temp2 = 1;
  
  //Check parameter locks
  mutex_lock(&my_mutex3);
  p = 1;
  mutex_lock(&my_mutex3);
  p = 2;
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
