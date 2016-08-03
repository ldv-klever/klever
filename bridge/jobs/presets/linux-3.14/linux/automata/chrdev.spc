OBSERVER AUTOMATON linux_chrdev
INITIAL STATE G0_C0_H0;


STATE USEALL G0_C0_H0 :
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G0_C0_H0;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) != 0} GOTO G0_C0_H1;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) != 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) == 0} GOTO G0_C0_H1;

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> SPLIT {((int)$1)==0} GOTO G0_C0_H1 NEGATION GOTO G0_C0_H0;
  MATCH CALL {ldv_unregister_chrdev_region($?)} -> ERROR("linux:chrdev::double deregistration");


STATE USEALL G0_C0_H1 :
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G0_C0_H1;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) != 0} ERROR("linux:chrdev::double registration");
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) != 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) == 0} ERROR("linux:chrdev::double registration");

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1)==0} ERROR("linux:chrdev::double registration");
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1)!=0} GOTO G0_C0_H1;
  MATCH CALL {ldv_unregister_chrdev_region($?)} -> GOTO G0_C0_H0;

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:chrdev::registered at exit");


STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON