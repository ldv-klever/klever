OBSERVER AUTOMATON linux_rculock
INITIAL STATE Init;

STATE USEFIRST Init :
  MATCH ENTRY -> ENCODE {int rcu_state = 0;} GOTO Init;
  MATCH CALL {ldv_rcu_read_lock($?)} -> ENCODE {rcu_state=rcu_state+1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock($?)} -> ERROR("linux:rculock::more unlocks");
  
STATE USEALL Inc :
  MATCH CALL {ldv_rcu_read_lock($?)} -> ENCODE {rcu_state=rcu_state+1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock($?)} -> ASSUME {rcu_state != 1;} ENCODE {rcu_state=rcu_state-1;} GOTO Inc;
  MATCH CALL {ldv_rcu_read_unlock($?)} -> ASSUME {rcu_state == 1;} ENCODE {rcu_state=rcu_state-1;} GOTO Init;
  MATCH CALL {ldv_check_for_read_section($?)} -> ERROR("linux:rculock::locked at read section");
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:rculock::locked at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON