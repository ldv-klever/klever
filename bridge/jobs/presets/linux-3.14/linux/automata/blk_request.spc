OBSERVER AUTOMATON linux_blk_request
INITIAL STATE Zero;

STATE USEALL Zero :
  MATCH RETURN {$1=ldv_blk_get_request($2)} -> ASSUME {((int)$2) == 16U; ((struct request *)$1) != 0} GOTO Got;
  MATCH RETURN {$1=ldv_blk_get_request($2)} -> ASSUME {((int)$2) == 208U; ((struct request *)$1) != 0} GOTO Got;
  MATCH RETURN {$1=ldv_blk_get_request($2)} -> ASSUME {((int)$2) != 16U; ((int)$2) != 208U; ((struct request *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_blk_get_request($2)} -> ASSUME {((struct request *)$1) != 0} GOTO Got;
  MATCH RETURN {$1=ldv_blk_get_request($2)} -> ASSUME {((struct request *)$1) == 0} GOTO Zero;
  MATCH RETURN {$1=ldv_blk_make_request($?)} -> ASSUME {((struct request *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_blk_make_request($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO Zero;
  MATCH RETURN {$1=ldv_blk_make_request($?)} -> ASSUME {((unsigned long)$1) <= 2012} GOTO Got;
  MATCH CALL {ldv_put_blk_rq($?)} -> ERROR("linux:blk:request::double put");

STATE USEFIRST Got :
  MATCH RETURN {$1=ldv_blk_get_request($?)} -> ERROR("linux:blk:request::double get");
  MATCH RETURN {$1=ldv_blk_make_request($?)} -> ERROR("linux:blk:request::double get");
  MATCH CALL {ldv_put_blk_rq($?)} -> GOTO Zero;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:blk:request::get at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON