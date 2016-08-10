OBSERVER AUTOMATON linux_netdev
INITIAL STATE Zero;

STATE USEALL Zero :
  MATCH RETURN {$1=ldv_pre_register_netdev($?)} -> ASSUME {((int)$1) < 0} GOTO Probe_error;
  MATCH RETURN {$1=ldv_pre_register_netdev($?)} -> ASSUME {((int)$1) >= 0} GOTO Zero;

STATE USEALL Probe_error :
  MATCH RETURN {$1=ldv_post_probe($?)} -> ASSUME {((int)$1)!=0} GOTO Zero;
  MATCH RETURN {$1=ldv_post_probe($?)} -> ASSUME {((int)$1)==0} ERROR("linux:netdev::wrong return value");
  MATCH CALL {ldv_reset_error_counter($?)} -> GOTO Zero;

END AUTOMATON