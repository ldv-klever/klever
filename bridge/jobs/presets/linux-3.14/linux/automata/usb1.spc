OBSERVER AUTOMATON linux_usb1
INITIAL STATE Init;

STATE USEALL Init :
  MATCH ENTRY -> ENCODE {int count = 0;} GOTO Init;

  MATCH RETURN {$2 = ldv_usb_get_dev($1)} ->
    ASSUME {((struct usb_device *)$1) != 0; ((struct usb_device *)$2) != 0} ENCODE {count=count+1;} GOTO Inc;
  MATCH RETURN {$2 = ldv_usb_get_dev($1)} -> ASSUME {((struct usb_device *)$1) == 0} GOTO Init;
  MATCH RETURN {$2 = ldv_usb_get_dev($1)} -> ASSUME {((struct usb_device *)$2) == 0} GOTO Init;
  MATCH CALL {ldv_usb_put_dev($1)} ->
    ASSUME {((struct usb_device *)$1) != 0} ERROR("linux:usb:resource:ref:unincremented counter decrement");
  // Same condition?
  MATCH CALL {ldv_usb_put_dev($1)} ->
    ASSUME {((struct usb_device *)$1) != 0} ERROR("linux:usb:resource:ref:less initial decrement");
  MATCH CALL {ldv_usb_put_dev($1)} -> ASSUME {((struct usb_device *)$1) == 0} GOTO Init;

STATE USEALL Inc :
  MATCH RETURN {$2 = ldv_usb_get_dev($1)} ->
    ASSUME {((struct usb_device *)$1) != 0; ((struct usb_device *)$2) != 0} ENCODE {count=count+1;} GOTO Inc;
  MATCH RETURN {$2 = ldv_usb_get_dev($1)} -> ASSUME {((struct usb_device *)$1) == 0} GOTO Inc;
  MATCH RETURN {$2 = ldv_usb_get_dev($1)} -> ASSUME {((struct usb_device *)$2) == 0} GOTO Inc;

  MATCH CALL {ldv_usb_put_dev($1)} -> ASSUME {((struct usb_device *)$1) != 0; count >  1} ENCODE {count=count-1;} GOTO Inc;
  MATCH CALL {ldv_usb_put_dev($1)} -> ASSUME {((struct usb_device *)$1) != 0; count == 1} ENCODE {count=count-1;} GOTO Init;
  MATCH CALL {ldv_usb_put_dev($1)} -> ASSUME {((struct usb_device *)$1) == 0} GOTO Inc;

  //MATCH CALL {ldv_check_return_value_probe($1)} -> ASSUME {((int)$1) == 0} GOTO Inc;
  //MATCH CALL {ldv_check_return_value_probe($1)} -> ASSUME {((int)$1) != 0} ERROR("get without put on failed probe");

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:usb:resource:ref:more initial at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON