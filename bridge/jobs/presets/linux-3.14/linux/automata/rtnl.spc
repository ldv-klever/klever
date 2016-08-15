OBSERVER AUTOMATON linux_rtnl
INITIAL STATE Unlocked;

STATE USEALL Unlocked :
  MATCH CALL {ldv_rtnl_lock($?)} -> GOTO Locked;
  MATCH CALL {ldv_rtnl_unlock($?)} -> ERROR("linux:rtnl::double unlock");
  MATCH RETURN {$1=ldv_rtnl_trylock($?)} -> ASSUME {((int)$1) != 0} GOTO Locked;
  MATCH RETURN {$1=ldv_rtnl_trylock($?)} -> ASSUME {((int)$1) == 0} GOTO Unlocked;

STATE USEALL Locked :
  MATCH CALL {ldv_rtnl_lock($?)} -> ERROR("linux:rtnl::double lock");
  MATCH CALL {ldv_ieee80211_unregister_hw($?)} -> ERROR("linux:rtnl::double lock");
  MATCH CALL {ldv_rtnl_trylock($?)} -> ERROR("linux:rtnl::double lock");
  MATCH RETURN {$1=ldv_rtnl_is_locked($?)} -> SPLIT {((int)$1) == 1} GOTO Locked NEGATION GOTO Stop;
  MATCH CALL {ldv_rtnl_unlock($?)} -> GOTO Unlocked;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:rtnl::lock on exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON