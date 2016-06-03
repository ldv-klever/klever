#include <linux/module.h>
#include <linux/init.h>

#define exchange struct ldvarg

struct mutex *ldv_envgen;

struct ldvarg {
	int one;
};

struct testdriver {
	exchange * (*handler)(exchange, exchange *);
};

int ldv_function(void);

static exchange * exch_handler(exchange arg1,exchange * arg2)
{
	mutex_lock(ldv_envgen);
	return &arg1;
};

static struct testdriver driver = {
	.handler =  exch_handler,
};

