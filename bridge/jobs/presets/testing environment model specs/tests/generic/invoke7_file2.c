#include <linux/module.h>
#include <linux/init.h>
#include "header.h"

extern struct mutex *ldv_envgen;

static void handler(int i)
{
	mutex_lock(ldv_envgen);
	return i;
};

static struct ldvdriver driver = {
	.handler =	handler
};

