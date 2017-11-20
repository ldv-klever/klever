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

//Test should check, how the value analysis handles loops

int global;

int g(int a) {
    return a + 1;
}

int my_main(void) {
  int i = 0;
  int res = 0;
  for (i = 0; i < 10000; i++) {
      res = g(res);
  }
  if (res < 10000) {
    global = 0;
  }
  return 0;
}

int ldv_main(void* arg) {
    global = 1;
	my_main();
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
