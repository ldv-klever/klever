OBSERVER AUTOMATON linux_rculockbh
INITIAL STATE Init;

STATE USEFIRST Init :
  MATCH ENTRY -> ENCODE {int rcu_nested_bh = 0;} GOTO Init;
  MATCH CALL {ldv_rcu_read_lock_bh($?)} -> ENCODE {rcu_nested_bh=rcu_nested_bh+1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock_bh($?)} -> ERROR("linux:rculockbh::more unlocks");
  
STATE USEALL Inc :
  MATCH CALL {ldv_rcu_read_lock_bh($?)} -> ENCODE {rcu_nested_bh=rcu_nested_bh+1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock_bh($?)} -> ASSUME {rcu_nested_bh != 1;} ENCODE {rcu_nested_bh=rcu_nested_bh-1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock_bh($?)} -> ASSUME {rcu_nested_bh == 1;} ENCODE {rcu_nested_bh=rcu_nested_bh-1;} GOTO Init;
  MATCH CALL {ldv_check_for_read_section($?)} -> ERROR("linux:rculockbh::locked at read section");
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:rculockbh::locked at exit");

END AUTOMATON