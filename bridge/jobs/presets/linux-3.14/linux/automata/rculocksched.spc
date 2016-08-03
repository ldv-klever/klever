OBSERVER AUTOMATON linux_rculocksched
INITIAL STATE Init;

STATE USEFIRST Init :
  MATCH ENTRY -> ENCODE {int rcu_nested_sched = 0;} GOTO Init;
  MATCH CALL {ldv_rcu_read_lock_sched($?)} -> ENCODE {rcu_nested_sched=rcu_nested_sched+1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock_sched($?)} -> ERROR("linux:rculocksched::more unlocks");
  
STATE USEALL Inc :
  MATCH CALL {ldv_rcu_read_lock_sched($?)} -> ENCODE {rcu_nested_sched=rcu_nested_sched+1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock_sched($?)} -> ASSUME {rcu_nested_sched != 1;} ENCODE {rcu_nested_sched=rcu_nested_sched-1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock_sched($?)} -> ASSUME {rcu_nested_sched == 1;} ENCODE {rcu_nested_sched=rcu_nested_sched-1;} GOTO Init;
  MATCH CALL {ldv_check_for_read_section($?)} -> ERROR("linux:rculocksched::locked at read section");
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:rculocksched::locked at exit");

END AUTOMATON