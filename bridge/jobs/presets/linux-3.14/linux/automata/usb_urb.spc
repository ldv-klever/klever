OBSERVER AUTOMATON linux_usb_urb
INITIAL STATE Init;

STATE USEALL Init :
  MATCH ENTRY -> ENCODE {int urb_state = 0;} GOTO Init;
  MATCH RETURN {$1=ldv_usb_alloc_urb($?)} -> ASSUME {((void *)$1) != ((void *)0)} ENCODE {urb_state=urb_state+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_usb_alloc_urb($?)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Init;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Init;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) != ((void *)0)} ERROR("linux:usb:urb::less initial decrement");

STATE USEALL Inc :
  MATCH RETURN {$1=ldv_usb_alloc_urb($?)} -> ASSUME {((void *)$1) != ((void *)0)} ENCODE {urb_state=urb_state+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_usb_alloc_urb($?)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Inc;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) != ((void *)0); urb_state > 1} ENCODE {urb_state=urb_state-1;} GOTO Inc;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) != ((void *)0); urb_state <= 1} ENCODE {urb_state=urb_state-1;} GOTO Init;
  MATCH CALL {ldv_usb_free_urb($1)} -> ASSUME {((void *)$1) == ((void *)0)} GOTO Inc;

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:usb:urb::more initial at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON