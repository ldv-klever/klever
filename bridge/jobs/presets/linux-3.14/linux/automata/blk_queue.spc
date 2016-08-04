OBSERVER AUTOMATON linux_blk_queue
INITIAL STATE Zero;

STATE USEALL Zero :
  MATCH RETURN {$1=ldv_request_queue($?)} -> ASSUME {((struct request_queue *)$1) != 0} GOTO Got;
  MATCH RETURN {$1=ldv_request_queue($?)} -> ASSUME {((struct request_queue *)$1) == 0} GOTO Zero;
  MATCH CALL {ldv_blk_cleanup_queue($?)} -> ERROR("linux:blk:queue::use before allocation");

STATE USEFIRST Got :
  MATCH RETURN {$1=ldv_request_queue($?)} -> ERROR("linux:blk:queue::double allocation");
  MATCH CALL {ldv_blk_cleanup_queue($?)} -> GOTO Zero;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:blk:queue::more initial at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON