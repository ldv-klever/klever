#include <linux/kernel.h>
#include <linux/module.h>
#include <net/sock.h>

static int __init init(void)
{
	struct sock *sk1;
        struct sock *sk2;

        lock_sock(sk1);
	lock_sock_nested(sk2,1);
	release_sock(sk1);
	release_sock(sk2);
	if (lock_sock_fast(sk1))
		unlock_sock_fast(sk1,false);
	
	lock_sock(sk1);
	unlock_sock_fast(sk1,true);

	return 0;
}

module_init(init);
