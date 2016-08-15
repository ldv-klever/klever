#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

int ldv_sysfs = 0;

/* MODEL_FUNC_DEF Create sysfs group. */
int ldv_sysfs_create_group(void *dummy)
{
	/* OTHER Choose an arbitrary return value. */
	int res = ldv_undef_int_nonpositive();
	/* OTHER If memory is not available. */
	if (!res) {
		/* CHANGE_STATE Increase allocated counter. */
		ldv_sysfs++;
		/* RETURN Sysfs group was successfully created. */
		return 0;
	}
	/* RETURN There was an error during sysfs group creation. */
	return res;
}

/* MODEL_FUNC_DEF Remove sysfs group. */
void ldv_sysfs_remove_group(void)
{
	/* ASSERT Sysfs group must be allocated before. */
	ldv_assert("linux:sysfs::less initial decrement", ldv_sysfs >= 1);
	/* CHANGE_STATE Decrease allocated counter. */
	ldv_sysfs--;
}

/* MODEL_FUNC_DEF Check that all sysfs groups are not incremented at the end */
void ldv_check_final_state( void )
{
	/* ASSERT Sysfs groups must be freed at the end. */
	ldv_assert("linux:sysfs::more initial at exit", ldv_sysfs == 0);
}
