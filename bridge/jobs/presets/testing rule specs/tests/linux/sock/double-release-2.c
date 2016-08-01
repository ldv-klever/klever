#include <linux/kernel.h>
#include <linux/module.h>
#include <net/sock.h>

static int __init init(void)
{
	struct sock *sk;

	unlock_sock_fast(sk, false);

	return 0;
}

module_init(init);
