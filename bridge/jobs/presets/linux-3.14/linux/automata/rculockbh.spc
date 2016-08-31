OBSERVER AUTOMATON linux_rculockbh
INITIAL STATE Init;

STATE USEFIRST Init :
  MATCH ENTRY -> ENCODE {int rcu_bh_state = 0;} GOTO Init;
  MATCH CALL {ldv_rcu_read_lock_bh($?)} -> ENCODE {rcu_bh_state=rcu_bh_state+1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock_bh($?)} -> ERROR("linux:rculockbh::more unlocks");
  
STATE USEALL Inc :
  MATCH CALL {ldv_rcu_read_lock_bh($?)} -> ENCODE {rcu_bh_state=rcu_bh_state+1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock_bh($?)} -> ASSUME {rcu_bh_state != 1;} ENCODE {rcu_bh_state=rcu_bh_state-1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock_bh($?)} -> ASSUME {rcu_bh_state == 1;} ENCODE {rcu_bh_state=rcu_bh_state-1;} GOTO Init;
  MATCH CALL {ldv_check_for_read_section($?)} -> ERROR("linux:rculockbh::locked at read section");
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:rculockbh::locked at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON