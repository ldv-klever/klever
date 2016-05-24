#include <linux/module.h>
#include <linux/init.h>

struct mutex *ldv_envgen;

struct ldvarg {
	int one;
};

struct testdriver {
	struct ldvarg * (*open)(struct ldvarg, struct ldvarg *);
};

int ldv_function(void);

static struct ldvarg * struct_handler(struct ldvarg arg1, struct ldvarg * arg2)
{
	mutex_lock(ldv_envgen);
	return &arg1;
};

static struct testdriver driver = {
	.open  	 =	struct_handler,
};

