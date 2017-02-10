#include <linux/kernel.h>
#include <linux/module.h>
#include <linux/device.h>
#include <linux/mutex.h>
#include <verifier/thread.h>

static DEFINE_MUTEX(my_mutex);

int gvar = 0;

void f(void* arg) {
	gvar = 1;
}

void g(void* arg) {
	int b;

	mutex_lock(&my_mutex);
	b = gvar;
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
