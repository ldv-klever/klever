#include <linux/module.h>
#include <linux/kernel.h>
#include <linux/clk.h>

static int __init init(void)
{
	struct clk *clk_1;
	struct clk *clk_2;
	if (!clk_enable(clk_1))
	{
		if (!clk_enable(clk_2))
			clk_disable(clk_2);
		clk_disable(clk_1);
	}
	return 0;
}

module_init(init);