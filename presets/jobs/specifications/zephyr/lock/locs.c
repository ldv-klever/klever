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

#include <verifier/common.h>
#include <verifier/memory.h>
#include <verifier/nondet.h>
#include <stdio.h>

int lock1 = -1;
int lock2 = -1;
int lock3 = -1;
int lock4 = -1;
int lock5 = -1;
int lock6 = -1;
int lock7 = -1;
int lock8 = -1;
int lock9 = -1;
int lock10 = -1;

int ldv_irq_lock(void) 
{
    int key = ldv_undef_int_positive();

    if (lock1 == -1) {
        lock1 = key;
        return lock1;
    }
    if (lock2 == -1) {
        lock2 = key;
        return lock2;
    }
    if (lock3 == -1) {
        lock3 = key;
        return lock3;
    }
    if (lock4 == -1) {
        lock4 = key;
        return lock4;
    }
    if (lock5 == -1) {
        lock5 = key;
        return lock5;
    }
    if (lock6 == -1) {
        lock6 = key;
        return lock6;
    }
    if (lock7 == -1) {
        lock7 = key;
        return lock7;
    }
    if (lock8 == -1) {
        lock8 = key;
        return lock8;
    }
    if (lock9 == -1) {
        lock9 = key;
        return lock9;
    }
    if (lock10 == -1) {
        lock10 = key;
        return lock10;
    }
    if (ldv_undef_int()) {
	    return ldv_undef_int_negative();
	} else {
	    ldv_assume(0);
    }
}

void ldv_irq_unlock(int key) 
{
    ldv_assert("zephyr::wrong key", key == lock1 || key == lock2 || key ==  lock3 || key ==  lock4 || key ==  lock5 || key ==  lock6 || key ==  lock7 || key ==  lock8 || key ==  lock9 || key ==  lock10);
    //проверки с конца (должно разблокировываться в обратном порядке, иначе дедлок)
    if (lock10 != -1) {
        ldv_assert("zephyr::deadlock", lock10 == key);
    } else if (lock9 != -1) {
        ldv_assert("zephyr::deadlock", lock9 == key);
    } else if (lock8 != -1) {
        ldv_assert("zephyr::deadlock", lock8 == key);
    } else if (lock7 != -1) {
        ldv_assert("zephyr::deadlock", lock7 == key);
    } else if (lock6 != -1) {
        ldv_assert("zephyr::deadlock", lock6 == key);
    } else if (lock5 != -1) {
        ldv_assert("zephyr::deadlock", lock5 == key);
    } else if (lock4 != -1) {
        ldv_assert("zephyr::deadlock", lock4 == key);
    } else if (lock3 != -1) {
        ldv_assert("zephyr::deadlock", lock3 == key);
    } else if (lock2 != -1) {
        ldv_assert("zephyr::deadlock", lock2 == key);
    } else if (lock1 != -1) {
        ldv_assert("zephyr::deadlock", lock1 == key);
    } else {
        ldv_assert("zephyr::missed lock", 0);
    }
    
}

void ldv_check_final_state(void)
{
    /* ASSERT Missed closing the first lock */
	ldv_assert("zephyr::missed unlock", lock1 == 0);
	/* ASSERT Missed closing the second lock */
	ldv_assert("zephyr::missed unlock", lock2 == 0);
	/* ASSERT Missed closing the third lock */
	ldv_assert("zephyr::missed unlock", lock3 == 0);
	/* ASSERT Missed closing the fourth lock */
	ldv_assert("zephyr::missed unlock", lock4 == 0);
	/* ASSERT Missed closing the fifth lock */
	ldv_assert("zephyr::missed unlock", lock5 == 0);
    /* ASSERT Missed closing the sixth lock */
	ldv_assert("zephyr::missed unlock", lock6 == 0);
	/* ASSERT Missed closing the seventh lock */
	ldv_assert("zephyr::missed unlock", lock7 == 0);
	/* ASSERT Missed closing the eighth lock */
	ldv_assert("zephyr::missed unlock", lock8 == 0);
	/* ASSERT Missed closing the ninth lock */
	ldv_assert("zephyr::missed unlock", lock9 == 0);
	/* ASSERT Missed closing the tenth lock */
	ldv_assert("zephyr::missed unlock", lock10 == 0);
}
