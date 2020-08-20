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

#include <linux/module.h>
#include <linux/mutex.h>
#include <ldv/verifier/nondet.h>
#include <ldv/verifier/thread.h>

void ldv_rcu_read_lock(void);
void ldv_rcu_read_unlock(void);
void ldv_rlock_rcu(void);
void ldv_runlock_rcu(void);
void * ldv_rcu_dereference(const void * pp);
void ldv_wlock_rcu(void);
void ldv_wunlock_rcu(void);
void ldv_free(void *);
void ldv_synchronize_rcu(void);
void ldv_rcu_assign_pointer(void * p1, const void * p2);

static DEFINE_MUTEX(ldv_lock);
static char * gp;

void *reader(void * arg) {
    char *a;
    char b;
    char * pReader = &b;

    ldv_rcu_read_lock();
    a = ({typeof(gp) p;
    ldv_rlock_rcu();
    p = ldv_rcu_dereference(gp);
    ldv_runlock_rcu();
    p;});
    b = *a;
    ldv_rcu_read_unlock();
    
    return 0;
}

void *writer1(void * arg) {
    char * pWriter = calloc(3, sizeof(int));
    // BUG: mutex_lock should be here
    char * ptr = gp;
                        
    pWriter[0] = 'r';
    
    pWriter[1] = 'c';
    pWriter[2] = 'u';

	mutex_lock(&ldv_lock);
    do {
        ldv_wlock_rcu();
        ldv_rcu_assign_pointer(gp, pWriter);
        ldv_wunlock_rcu();
    } while(0);
	mutex_unlock(&ldv_lock);
    ldv_synchronize_rcu();
    ldv_free(ptr);

    return NULL;
}

void *writer2(void * arg) {
    char * pWriter = calloc(3, sizeof(int));
    // BUG: mutex_lock should be here
    char * ptr = gp;
                        
    pWriter[0] = 'r';
    pWriter[1] = 'c';
    pWriter[2] = 'u';

	mutex_lock(&ldv_lock);
    do {
        ldv_wlock_rcu();
        ldv_rcu_assign_pointer(gp, pWriter);
        ldv_wunlock_rcu();
    } while(0);
	mutex_unlock(&ldv_lock);
    ldv_synchronize_rcu();
    ldv_free(ptr);

    return NULL;
}


static int __init ldv_init(void)
{
	pthread_attr_t const *attr = ldv_undef_ptr();
	void *arg1 = ldv_undef_ptr(), *arg2 = ldv_undef_ptr(), *arg3 = ldv_undef_ptr();
    pthread_t rd, wr1, wr2;

    gp = calloc(3, sizeof(int));

    pthread_mutex_init(&mutex, ((void *)0));
    pthread_create(&rd, attr, reader, arg1);
    pthread_create(&wr1, attr, writer1, arg2);
    pthread_create(&wr2, attr, writer2, arg3);

    return 0;
}

module_init(ldv_init);
