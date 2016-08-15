OBSERVER AUTOMATON linux_usb_register
INITIAL STATE Zero;

STATE USEALL Zero :
  MATCH RETURN {$1=ldv_pre_usb_register_driver($?)} -> ASSUME {((int)$1) < 0} GOTO Probe_error;
  MATCH RETURN {$1=ldv_pre_usb_register_driver($?)} -> ASSUME {((int)$1) >= 0} GOTO Zero;

STATE USEALL Probe_error :
  MATCH CALL {ldv_check_return_value_probe($1)} -> ASSUME {((int)$1)!=0} GOTO Zero;
  MATCH CALL {ldv_check_return_value_probe($1)} -> ASSUME {((int)$1)==0} ERROR("linux:usb:register::wrong return value");
  MATCH CALL {ldv_reset_error_counter($?)} -> GOTO Zero;

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON