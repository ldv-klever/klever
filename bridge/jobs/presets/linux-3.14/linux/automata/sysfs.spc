OBSERVER AUTOMATON linux_sysfs
INITIAL STATE Init;

STATE USEALL Init :
  MATCH ENTRY -> ENCODE {int sysfs = 0;} GOTO Init;
  MATCH RETURN {$1=ldv_sysfs_create_group($?)} -> ASSUME {((int)$1) == 0} ENCODE {sysfs=sysfs+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_sysfs_create_group($?)} -> ASSUME {((int)$1) <  0} GOTO Init;
  MATCH RETURN {$1=ldv_sysfs_create_group($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;
  MATCH CALL {ldv_sysfs_remove_group($?)} -> ERROR("linux:sysfs::less initial decrement");

STATE USEALL Inc :
  MATCH RETURN {$1=ldv_sysfs_create_group($?)} -> ASSUME {((int)$1) == 0} ENCODE {sysfs=sysfs+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_sysfs_create_group($?)} -> ASSUME {((int)$1) <  0} GOTO Inc;
  MATCH RETURN {$1=ldv_sysfs_create_group($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;
  MATCH CALL {ldv_sysfs_remove_group($?)} -> ASSUME {sysfs >  1} ENCODE {sysfs=sysfs-1;} GOTO Inc;
  MATCH CALL {ldv_sysfs_remove_group($?)} -> ASSUME {sysfs <= 1} ENCODE {sysfs=sysfs-1;} GOTO Init;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:sysfs::more initial at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON