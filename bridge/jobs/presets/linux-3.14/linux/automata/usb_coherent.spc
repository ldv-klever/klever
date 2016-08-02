OBSERVER AUTOMATON linux_usb_coherent
INITIAL STATE Init;

STATE USEALL Init :
  MATCH ENTRY -> ENCODE {int state_coh = 0;} GOTO Init;
  MATCH RETURN {$1=ldv_usb_alloc_coherent($?)} -> ASSUME {((void *)$1) != ((void *)0)} ENCODE {state_coh=state_coh+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_usb_alloc_coherent($?)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Init;
  MATCH CALL {ldv_usb_free_coherent($1)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Init;
  MATCH CALL {ldv_usb_free_coherent($1)} -> ASSUME {((void *)$1) != ((void *)0)} ERROR("linux:usb:coherent::less initial decrement");

STATE USEALL Inc :
  MATCH RETURN {$1=ldv_usb_alloc_coherent($?)} -> ASSUME {((void *)$1) != ((void *)0)} ENCODE {state_coh=state_coh+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_usb_alloc_coherent($?)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Inc;
  MATCH CALL {ldv_usb_free_coherent($1)} -> ASSUME {((void *)$1) != ((void *)0); state_coh > 1;} ENCODE {state_coh=state_coh-1;} GOTO Inc;
  MATCH CALL {ldv_usb_free_coherent($1)} -> ASSUME {((void *)$1) != ((void *)0); state_coh <= 1;} ENCODE {state_coh=state_coh-1;} GOTO Init;
  MATCH CALL {ldv_usb_free_coherent($1)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Inc;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:usb:coherent::more initial at exit");

END AUTOMATON