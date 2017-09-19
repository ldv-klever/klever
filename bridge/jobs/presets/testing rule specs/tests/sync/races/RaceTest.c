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

int false_unsafe, global;
int true_unsafe;
int unsafe, false_unsafe2;

static DEFINE_MUTEX(my_mutex);
static DEFINE_MUTEX(my_mutex2);

__inline static int local_init(int mutex ) 
{ 
  int mtx, rt ;

  if (mutex == (unsigned int )(138 << 24)) {
    if (rt) {
      return (0);
    }
    mutex_lock(&my_mutex);
    if (mtx != 0) {
      return (mtx);
    } 
    mutex_unlock(&my_mutex);
  }
  return (0);
}

 __inline static int tryLock(int id___0) 
{ 
  int idx ;
  if (id___0 == 0) {
    return (0);
  }
  mutex_lock(&my_mutex);
  if (id___0 == idx) {
    return (1);
  } 
  mutex_unlock(&my_mutex);
  return 0;
}

__inline static int get(int mutex ) 
{ 
  int rt, mtx, tmp___1 ;

  if (mutex == 0) {
    return (0);
  }
  mtx = tryLock(rt);
  if (mtx != 0) {
    return (mtx);
  } 
  tmp___1 = local_init(mutex);
  return (tmp___1);
}
 
__inline static int check(int code ) 
{ 
  int tmp;
  if (code == 27) {
    tmp = tryLock(tmp);
    if (tmp == 0) {
      return (28);
    }
  }
  return code;
}

int difficult_function(void) {
	int ret, param, mutex;
    ret = get(mutex);
    if (ret == 0) {
      return 28;
    }
restart: 
    false_unsafe = 0;
    true_unsafe = 0;
  
  mutex_unlock(&my_mutex);
  ret = check(param); 
  if (ret == 27) {
    goto restart;
  }
  unsafe = 1;
  true_unsafe = 0;
  return 0;
}


int f(int i) {
	if (i >= 0) {
      mutex_lock(&my_mutex2);
      false_unsafe2 = 1;
      mutex_unlock(&my_mutex2);
    } else {
      false_unsafe2 = 1;
    }
    return 0;
}

int g(void) {
	global = 1;
	return 0;
}

int my_main(int i) {
	difficult_function();
	g();
	f(i);
	return 0;
}

int ldv_main(void* arg) {
	my_main(0);
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
