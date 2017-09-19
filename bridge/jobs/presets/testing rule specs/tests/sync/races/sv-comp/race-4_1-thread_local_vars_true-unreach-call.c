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

int __VERIFIER_nondet_int(void);

pthread_t t1, t2;
DEFINE_MUTEX(mutex);
int pdev;

void ath9k_flush(void) {
   mutex_lock(&mutex);
   pdev = 6;
   mutex_unlock(&mutex);
}

//[[thread ath9k]]
void *thread_ath9k(void *arg) {
    while(1) {
      switch(__VERIFIER_nondet_int()) {
	      case 1:
        	//depend on ieee80211_register_hw which enables it
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
   if(__VERIFIER_nondet_int()) {
      pthread_create(&t2, 0, thread_ath9k, 0);
      return 0;
   }
   return -1;
}

void ieee80211_deregister_hw(void) {
   void *status;
   pthread_join(t2, &status);
   return;
}

static int ath_ahb_probe(void)
{
        int error;
        /* Register with mac80211 */
        error = ieee80211_register_hw();
        if (error)
                goto rx_cleanup;
        return 0;
rx_cleanup:
        return -1;
}

void ath_ahb_disconnect(void) {
        ieee80211_deregister_hw();
}

//thread local variables
int ldv_usb_state;

//[[thread usb]]
void *thread_usb(void *arg) {
    int probe_ret;
    ldv_usb_state = 0;
    while(1) {
      switch(__VERIFIER_nondet_int()) {
		case 0:
                if(ldv_usb_state==0) {
		  probe_ret = ath_ahb_probe();
		  if(probe_ret!=0)
		    goto exit_thread_usb;
                  ldv_usb_state = 1;
		  //race
		  //pdev = 7;
                }
		break;
		case 1:
                if(ldv_usb_state==1) {
                   ath_ahb_disconnect();
		   ldv_usb_state=0;
		   //not a race
		   pdev = 8;
                }
		break;
		case 2:
                if(ldv_usb_state==0) {
                  goto exit_thread_usb;
		}
		break;
      }    
    }
exit_thread_usb: 
    //not a race
    pdev = 9;
    return 0;
}


int start(void) {
   //not a race
   pdev = 1;
   if(__VERIFIER_nondet_int()) {
      pthread_create(&t1, 0, thread_usb, 0);
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
