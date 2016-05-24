#include <linux/module.h>
#include <linux/init.h>
#include "header.h"

struct mutex *ldv_envgen;

void handler(int arg)
{
	mutex_lock(ldv_envgen);
};

static struct ldvdriver driver = {
	.handler =	handler
};

