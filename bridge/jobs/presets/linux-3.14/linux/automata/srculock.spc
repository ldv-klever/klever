OBSERVER AUTOMATON linux_srculock
INITIAL STATE Init;

STATE USEFIRST Init :
  MATCH ENTRY -> ENCODE {int srcu_nested = 0;} GOTO Init;
  MATCH CALL {ldv_srcu_read_lock($?)} -> ENCODE {srcu_nested=srcu_nested+1;} GOTO Inc;
  MATCH CALL {ldv_srcu_read_unlock($?)} -> ERROR("linux:srculock::more unlocks");
  
STATE USEALL Inc :
  MATCH CALL {ldv_srcu_read_lock($?)} -> ENCODE {srcu_nested=srcu_nested+1;} GOTO Inc;
  MATCH CALL {ldv_srcu_read_unlock($?)} -> ASSUME {srcu_nested != 1;} ENCODE {srcu_nested=srcu_nested-1;} GOTO Inc;
  MATCH CALL {ldv_srcu_read_unlock($?)} -> ASSUME {srcu_nested == 1;} ENCODE {srcu_nested=srcu_nested-1;} GOTO Init;
  MATCH CALL {ldv_check_for_read_section($?)} -> ERROR("linux:srculock::locked at read section");
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:srculock::locked at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON