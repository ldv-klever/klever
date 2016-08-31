OBSERVER AUTOMATON linux_sock
INITIAL STATE Init;

STATE USEALL Init :
  MATCH ENTRY -> ENCODE {int sock_state = 0;} GOTO Init;
  MATCH CALL {ldv_lock_sock($?)} -> ENCODE {sock_state=sock_state+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_lock_sock_fast($?)} -> ASSUME {((int)$1) != 0} ENCODE {sock_state=sock_state+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_lock_sock_fast($?)} -> ASSUME {((int)$1) == 0} GOTO Init;
  MATCH CALL {ldv_unlock_sock($?)} -> ERROR("linux:sock::double release");

STATE USEALL Inc :
  MATCH CALL {ldv_lock_sock($?)} -> ENCODE {sock_state=sock_state+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_lock_sock_fast($?)} -> ASSUME {((int)$1) != 0} ENCODE {sock_state=sock_state+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_lock_sock_fast($?)} -> ASSUME {((int)$1) == 0} GOTO Inc;
  MATCH CALL {ldv_unlock_sock($?)} -> ASSUME {sock_state >  1} ENCODE {sock_state=sock_state-1;} GOTO Inc;
  MATCH CALL {ldv_unlock_sock($?)} -> ASSUME {sock_state <= 1} ENCODE {sock_state=sock_state-1;} GOTO Init;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:sock::all locked sockets must be released");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON