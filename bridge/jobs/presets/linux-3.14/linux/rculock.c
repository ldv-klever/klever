#include <linux/ldv/common.h>
#include <verifier/common.h>
#include <verifier/nondet.h>

/* CHANGE_STATE Indicates the level of rcu_lock nesting.*/
int ldv_rcu_nested = 0;

/* MODEL_FUNC_DEF Entry in rcu_read_lock/unlock section.*/
void ldv_rcu_read_lock(void)
{
   /* CHANGE_STATE Increments the level of rcu_read_lock nesting.*/
   ldv_rcu_nested++;
}

/* MODEL_FUNC_DEF Exit from rcu_read_lock/unlock section.*/
void ldv_rcu_read_unlock(void)
{
	/* ASSERT checks the count of opened rcu_lock sections.*/
	ldv_assert("linux:rculock:more unlocks", ldv_rcu_nested > 0);
	/* CHANGE_STATE Decrements the level of rcu_lock nesting.*/
	ldv_rcu_nested--;
}

/* MODEL_FUNC_DEF Checks that all rcu_lock sections are closed at read sections.*/
void ldv_check_for_read_section( void )
{
	/* ASSERT checks the count of opened rcu_lock sections.*/
	ldv_assert("linux:rculock:locked at read section", ldv_rcu_nested == 0);
}

/* MODEL_FUNC_DEF Checks that all rcu_lock sections are closed at exit.*/
void ldv_check_final_state( void )
{
	/* ASSERT checks the count of opened rcu_lock sections.*/
	ldv_assert("linux:rculock:locked at exit", ldv_rcu_nested == 0);
}
