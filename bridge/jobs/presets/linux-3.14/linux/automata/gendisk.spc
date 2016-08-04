OBSERVER AUTOMATON linux_gendisk
INITIAL STATE Init;

STATE USEALL Init :
  MATCH RETURN {$1 = ldv_alloc_disk($?)} -> ASSUME {((struct gendisk *)$1) != 0} GOTO Allocated;
  MATCH RETURN {$1 = ldv_alloc_disk($?)} -> ASSUME {((struct gendisk *)$1) == 0} GOTO Init;
  MATCH CALL {ldv_add_disk($?)} -> ERROR("linux:gendisk::use before allocation");
  MATCH CALL {ldv_del_gendisk($?)} -> ERROR("linux:gendisk::delete before add");
  MATCH CALL {ldv_put_disk($1)} -> ASSUME {((struct gendisk *)$1) != 0} ERROR("linux:gendisk::free before allocation");
  MATCH CALL {ldv_put_disk($1)} -> ASSUME {((struct gendisk *)$1) == 0} GOTO Init;

STATE USEALL Allocated :
  MATCH RETURN {$1 = ldv_alloc_disk($?)} -> ERROR("linux:gendisk::double allocation");
  MATCH CALL {ldv_add_disk($?)} -> GOTO Added;
  MATCH CALL {ldv_del_gendisk($?)} -> ERROR("linux:gendisk::delete before add");
  MATCH CALL {ldv_put_disk($1)} -> ASSUME {((struct gendisk *)$1) != 0} GOTO Init;
  MATCH CALL {ldv_put_disk($1)} -> ASSUME {((struct gendisk *)$1) == 0} GOTO Allocated;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:gendisk::more initial at exit");

STATE USEALL Added :
  MATCH RETURN {$1 = ldv_alloc_disk($?)} -> ERROR("linux:gendisk::double allocation");
  MATCH CALL {ldv_add_disk($?)} -> ERROR("linux:gendisk::use before allocation");
  MATCH CALL {ldv_del_gendisk($?)} -> GOTO Allocated;
  MATCH CALL {ldv_put_disk($1)} -> ASSUME {((struct gendisk *)$1) != 0} GOTO Init;
  MATCH CALL {ldv_put_disk($1)} -> ASSUME {((struct gendisk *)$1) == 0} GOTO Added;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:gendisk::more initial at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON