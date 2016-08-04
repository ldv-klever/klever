OBSERVER AUTOMATON AUTOMATON_10_1a
INITIAL STATE Unlocked;

STATE USEALL Unlocked :
  MATCH CALL {ldv_switch_to_interrupt_context($?)} -> GOTO Locked;

STATE USEALL Locked :
  MATCH CALL {ldv_switch_to_process_context($?)} -> GOTO Unlocked;
  MATCH CALL {ldv_check_alloc_flags($1)} -> ASSUME {((int)$1)==32} GOTO Locked;
  MATCH CALL {ldv_check_alloc_flags($1)} -> ASSUME {((int)$1)!=32} ERROR("linux:alloc:irq::wrong flags");
  MATCH CALL {ldv_check_alloc_nonatomic($?)} -> ERROR("linux:alloc:irq::nonatomic");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON