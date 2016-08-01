#include <linux/kernel.h>
#include <linux/module.h>
#include <net/sock.h>

static int __init init(void)
{
	struct sock *sk;

	lock_sock(sk);

	return 0;
}

module_init(init);
