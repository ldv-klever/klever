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

static DEFINE_MUTEX(ldv_lock);
int __ldv_pdev;
pthread_t thread, thread2;
int ldv_usb_state;

void ath9k_flush(void) {
     mutex_lock(&ldv_lock);
     __ldv_pdev = 6;
     mutex_unlock(&ldv_lock);
}

void* thread_ath9k(void *arg) {
     while(1) {
          switch(ldv_undef_int()) {
          case 1:
               ath9k_flush();
               break;
          case 2:
               goto exit_thread_ath9k;
          }
     }

exit_thread_ath9k:
     return 0;
}

int ieee80211_register_hw(void) {
     if(ldv_undef_int()) {
          pthread_create(&thread2, 0, &thread_ath9k, ((void *)0));
          return 0;
     }
     return -1;
}

void ieee80211_deregister_hw(void) {
     void *status;
     pthread_join(thread2, &status);
     return;
}

static int ath_ahb_probe(void)
{
     int error;

     error = ieee80211_register_hw();
     if (error)
          goto rx_cleanup;
     return 0;

rx_cleanup:
     return -1;
}

void ath_ahb_disconnect(void) {
     ieee80211_deregister_hw();
     return;
}

void* thread_usb(void *arg) {
     int probe_ret;
     ldv_usb_state = 0;

     while(1) {
          switch (ldv_undef_int()) {
          case 0:
               if (ldv_usb_state==0) {
                    probe_ret = ath_ahb_probe();
                    if (probe_ret!=0)
                         goto exit_thread_usb;
                    ldv_usb_state = 1;
               }
               break;
          case 1:
               if (ldv_usb_state==1) {
                    ath_ahb_disconnect();
                    ldv_usb_state=0;

                    __ldv_pdev = 8;
               }
               break;
          case 2:
               if (ldv_usb_state==0) {
                    goto exit_thread_usb;
               }
               break;
          }
     }
exit_thread_usb:

     __ldv_pdev = 9;
     return 0;
}

static int __init ldv_init(void) {
     __ldv_pdev = 1;

     if (ldv_undef_int()) {
          pthread_create(&thread, 0, &thread_usb, 0);
          return 0;
     }

     __ldv_pdev = 3;
     return -1;
}

static void __exit ldv_exit(void) {
     void *status;
     pthread_join(thread, &status);

     __ldv_pdev = 5;
}

module_init(ldv_init);
module_exit(ldv_exit);
