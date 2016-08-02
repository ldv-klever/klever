OBSERVER AUTOMATON mutex_usb_urb
INITIAL STATE Init;

STATE USEALL Init :
  MATCH ENTRY -> ENCODE {int state_urb = 0;} GOTO Init;
  MATCH RETURN {$1=ldv_usb_alloc_urb($?)} -> ASSUME {((void *)$1) != ((void *)0)} ENCODE {state_urb=state_urb+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_usb_alloc_urb($?)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Init;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Init;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) != ((void *)0)} ERROR("linux:usb:urb::less initial decrement");

STATE USEALL Inc :
  MATCH RETURN {$1=ldv_usb_alloc_urb($?)} -> ASSUME {((void *)$1) != ((void *)0)} ENCODE {state_urb=state_urb+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_usb_alloc_urb($?)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Inc;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) != ((void *)0); state_urb > 1} ENCODE {state_urb=state_urb-1;} GOTO Inc;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) != ((void *)0); state_urb <= 1} ENCODE {state_urb=state_urb-1;} GOTO Init;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Inc;

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:usb:urb::more initial at exit");

END AUTOMATON