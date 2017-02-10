#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(my_mutex);

int gvar = 0;
int global1 = 0;
int global2 = 0;
int global3 = 0;
int global4 = 0;
int global5 = 0;
int global6 = 0;
int global7 = 0;
int global8 = 0;
int global9 = 0;

void f(void* arg) {
	gvar = 1;
    global1 = 1;
    global2 = 1;
    global3 = 1;
    global4 = 1;
    global5 = 1;
    global6 = 1;
    global7 = 1;
    global8 = 1;
    global9 = 1;
}

void g(void* arg) {
	int b;
	mutex_lock(&my_mutex);
	b = gvar;
	b = global1;
	b = global2;
	b = global3;
	b = global4;
	b = global5;
	b = global6;
	b = global7;
	b = global8;
	b = global9;
	mutex_unlock(&my_mutex);
}

static int __init init(void)
{
    struct ldv_thread thread1, thread2;

    ldv_thread_create(&thread1, &f, 0);
    ldv_thread_create(&thread2, &g, 0);
    return 0;
}

module_init(init);

