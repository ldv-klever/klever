OBSERVER AUTOMATON linux_rwlock
INITIAL STATE R0_W0;

STATE USEALL R0_W0 :
  MATCH ENTRY -> ENCODE {int rlock = 0;} GOTO R0_W0;

  MATCH CALL {ldv_read_lock($?)} -> ENCODE {rlock=1;} GOTO R1_W0;
  MATCH CALL {ldv_read_unlock($?)} -> ERROR("linux:rwlock::more read unlocks");
  MATCH CALL {ldv_write_lock($?)} -> GOTO R0_W1;
  MATCH CALL {ldv_write_unlock($?)} -> ERROR("linux:rwlock::double write unlock");

  MATCH RETURN {$1=ldv_read_trylock($?)} -> ASSUME {((int)$1)==1} ENCODE {rlock=1;} GOTO R1_W0;
  MATCH RETURN {$1=ldv_write_trylock($?)} -> ASSUME {((int)$1)==1} GOTO R0_W1;


STATE USEALL R0_W1 :
  MATCH CALL {ldv_read_lock($?)} -> ERROR("linux:rwlock::read lock on write lock");
  MATCH CALL {ldv_read_unlock($?)} -> ERROR("linux:rwlock::more read unlocks");
  MATCH CALL {ldv_write_lock($?)} -> ERROR("linux:rwlock::double write lock");
  MATCH CALL {ldv_write_unlock($?)} -> GOTO R0_W0;

  MATCH RETURN {$1=ldv_read_trylock($?)} -> ASSUME {((int)$1)==1} ERROR("read lock with write lock");
  MATCH RETURN {$1=ldv_write_trylock($?)} -> ASSUME {((int)$1)==1} ERROR("double write lock");

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:rwlock::write lock at exit");


STATE USEALL R1_W0 :
  MATCH CALL {ldv_read_lock($?)} -> ENCODE {rlock=rlock+1;} GOTO R1_W0;
  MATCH CALL {ldv_read_unlock($?)} -> ASSUME {rlock >  1;} ENCODE {rlock=rlock-1;} GOTO R1_W0;
  MATCH CALL {ldv_read_unlock($?)} -> ASSUME {rlock <= 1;} ENCODE {rlock=0;} GOTO R0_W0;
  MATCH CALL {ldv_write_lock($?)} -> GOTO R1_W1;
  MATCH CALL {ldv_write_unlock($?)} -> ERROR("linux:rwlock::double write unlock");

  MATCH RETURN {$1=ldv_read_trylock($?)} -> ASSUME {((int)$1)==1} ENCODE {rlock=rlock+1;} GOTO R1_W0;
  MATCH RETURN {$1=ldv_write_trylock($?)} -> ASSUME {((int)$1)==1} GOTO R1_W1;

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:rwlock::read lock at exit");


STATE USEALL R1_W1 :
  MATCH CALL {ldv_read_lock($?)} -> ERROR("linux:rwlock::read lock on write lock");
  MATCH CALL {ldv_read_unlock($?)} -> ASSUME {rlock >  1;} ENCODE {rlock=rlock-1;} GOTO R1_W1;
  MATCH CALL {ldv_read_unlock($?)} -> ASSUME {rlock <= 1;} ENCODE {rlock=0;} GOTO R0_W1;
  MATCH CALL {ldv_write_lock($?)} -> ERROR("linux:rwlock::double write lock");
  MATCH CALL {ldv_write_unlock($?)} -> GOTO R1_W0;

  MATCH RETURN {$1=ldv_read_trylock($?)} -> ASSUME {((int)$1)==1} ERROR("read lock with write lock");
  MATCH RETURN {$1=ldv_write_trylock($?)} -> ASSUME {((int)$1)==1} ERROR("double write lock");

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:rwlock::read lock at exit");
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:rwlock::write lock at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON