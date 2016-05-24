#include <linux/module.h>
#include <linux/init.h>

struct mutex *ldv_envgen;

enum our_enum {
	a,
	b,
	c
};

struct testdriver {
	enum our_enum * (*close)(enum our_enum, enum our_enum *);
};

int ldv_function(void);



static enum our_enum * enum_handler(enum our_enum arg1, enum our_enum * arg2)
{
	mutex_lock(ldv_envgen);
	return &arg1;
};

static struct testdriver driver = {
	.close 	 =	enum_handler,
};

