#include <linux/module.h>
#include <linux/init.h>
#include "header.h"

extern struct mutex *ldv_envgen;

void handler1(int arg)
{
	mutex_lock(ldv_envgen);
};

static struct ldvdriver driver = {
	.handler =	handler1
};

