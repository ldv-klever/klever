OBSERVER AUTOMATON linux_class
INITIAL STATE G0_C0_H0;


STATE USEALL G0_C0_H0 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C0_H0;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO G0_C1_H0;

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) == 0} GOTO G0_C1_H0;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C0_H0;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} -> ERROR("linux:class::double registration");

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G0_C0_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C0_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} ERROR("linux:class::double registration");


STATE USEALL G0_C1_H0 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C1_H0;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} ERROR("linux:class::double registration");

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) == 0} ERROR("linux:class::double registration");
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C1_H0;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} -> GOTO G0_C0_H0;

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G0_C1_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C1_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO G0_C0_H0;

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:class::registered at exit");


STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON