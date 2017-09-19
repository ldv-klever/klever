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

static DEFINE_MUTEX(mutex);
extern int __VERIFIER_nondet_int(void);

pthread_t t1;
int pdev;

void *thread1(void *arg) {
   mutex_lock(&mutex);
   pdev = 6;
   mutex_unlock(&mutex);
}

int start(void) {
   //not a race
   pdev = 1;
   if(__VERIFIER_nondet_int()) {
      //enable thread 1
      pthread_create(&t1, 0, thread1, 0);
      //race
      //pdev = 2;
      return 0;
   }
   //not a race
   pdev = 3;
   return -1;
}

void stop(void) {
   void *status;
   //race
   //pdev = 4;
   pthread_join(t1, &status);
   //not a race
   pdev = 5;
}

void* ldv_main(void* arg) {
    if(start()!=0) goto exit;
    stop();
exit:
    return 0;
}


static int __init init(void)
{
	pthread_t thread2;

	pthread_create(&thread2, 0, ldv_main, 0);
	return 0;
}

module_init(init);
