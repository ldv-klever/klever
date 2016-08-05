#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* CHANGE_STATE Indicates the level of srcu_lock nesting */
int ldv_srcu_nested = 0;

/* MODEL_FUNC_DEF Entry in srcu_read_lock/unlock section */
void ldv_srcu_read_lock(void)
{
	/* CHANGE_STATE Increments the level of srcu_read_lock nesting */
	ldv_srcu_nested++;
}

/* MODEL_FUNC_DEF Exit from srcu_read_lock/unlock section */
void ldv_srcu_read_unlock(void)
{
	/* ASSERT checks the count of opened srcu_lock sections */
	ldv_assert("linux:srculock::more unlocks", ldv_srcu_nested > 0);
	/* CHANGE_STATE Decrements the level of srcu_lock nesting */
	ldv_srcu_nested--;
}

/* MODEL_FUNC_DEF Checks that all srcu_lock sections are closed at read sections */
void ldv_check_for_read_section( void )
{
	/* ASSERT checks the count of opened srcu_lock sections */
	ldv_assert("linux:srculock::locked at read section", ldv_srcu_nested == 0);
}

/* MODEL_FUNC_DEF Checks that all srcu_lock sections are closed at exit.*/
void ldv_check_final_state( void )
{
	/* ASSERT checks the count of opened srcu_lock sections */
	ldv_assert("linux:srculock::locked at exit", ldv_srcu_nested == 0);
}
