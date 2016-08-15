OBSERVER AUTOMATON linux_alloc_usblock
INITIAL STATE Unlocked;

STATE USEALL Unlocked :
  MATCH CALL {ldv_usb_lock_device($?)} -> GOTO Locked;
  MATCH RETURN {$1=ldv_usb_trylock_device($?)} -> SPLIT {((int)$1)!=0} GOTO Locked NEGATION GOTO Unlocked;
  MATCH RETURN {$1=ldv_usb_lock_device_for_reset($?)} -> SPLIT {((int)$1)==0} GOTO Locked NEGATION GOTO Unlocked;

STATE USEALL Locked :
  MATCH CALL {ldv_usb_unlock_device($?)} -> GOTO Unlocked;
  MATCH CALL {ldv_check_alloc_flags($1)} -> ASSUME {((int)$1)!=16; ((int)$1)!=32} ERROR("linux:alloc:usb lock::wrong flags");
  MATCH CALL {ldv_check_alloc_flags($1)} -> ASSUME {((int)$1)==32} GOTO Locked;
  MATCH CALL {ldv_check_alloc_flags($1)} -> ASSUME {((int)$1)==16} GOTO Locked;
  MATCH CALL {ldv_check_alloc_nonatomic($?)} ->  ERROR("linux:alloc:usb lock::nonatomic");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON