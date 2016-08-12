OBSERVER AUTOMATON linux_usb_gadget
INITIAL STATE G0_C0_H0;


STATE USEALL G0_C0_H0 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C0_H0;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO G0_C1_H0;

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) == 0} GOTO G0_C1_H0;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C0_H0;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} -> GOTO Stop;

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G0_C0_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C0_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO Stop;

  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G0_C0_H0;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) != 0} GOTO G0_C0_H1;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) != 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) == 0} GOTO G0_C0_H1;

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) == 0} GOTO G0_C0_H1;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C0_H0;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_chrdev_region($?)} -> GOTO Stop;

  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> SPLIT {((int)$1)==0} GOTO G1_C0_H0 NEGATION GOTO G0_C0_H0;
  MATCH CALL {ldv_unregister_usb_gadget($?)} -> ERROR("linux:usb:gadget::double usb gadget deregistration");


STATE USEALL G0_C1_H0 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C1_H0;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO Stop;

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C1_H0;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} -> GOTO G0_C0_H0;

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G0_C1_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C1_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO G0_C0_H0;

  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G0_C1_H0;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) != 0} GOTO G0_C1_H1;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) != 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) == 0} GOTO G0_C1_H1;

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) == 0} GOTO G0_C1_H1;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C1_H0;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_chrdev_region($?)} -> GOTO Stop;

  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> SPLIT {((int)$1)==0} GOTO G1_C1_H0 NEGATION GOTO G0_C1_H0;
  MATCH CALL {ldv_unregister_usb_gadget($?)} -> ERROR("linux:usb:gadget::double usb gadget deregistration");


STATE USEALL G0_C0_H1 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C0_H1;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO G0_C1_H1;

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) == 0} GOTO G0_C1_H1;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C0_H1;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} -> GOTO Stop;

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G0_C0_H1;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C0_H1;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO Stop;

  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G0_C0_H1;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >= 0} GOTO Stop;

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C0_H1;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_chrdev_region($?)} -> GOTO G0_C0_H0;

  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> SPLIT {((int)$1)==0} GOTO G1_C0_H1 NEGATION GOTO G0_C0_H1;
  MATCH CALL {ldv_unregister_usb_gadget($?)} -> ERROR("linux:usb:gadget::double usb gadget deregistration");


STATE USEALL G0_C1_H1 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C1_H1;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO Stop;

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C1_H1;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} -> GOTO G0_C0_H1;

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G0_C1_H1;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G0_C1_H1;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0} GOTO G0_C0_H1;

  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G0_C0_H1;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >= 0} GOTO Stop;

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) <  0} GOTO G0_C1_H1;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_chrdev_region($?)} -> GOTO G0_C1_H0;

  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> SPLIT {((int)$1)==0} GOTO G1_C1_H1 NEGATION GOTO G0_C1_H1;
  MATCH CALL {ldv_unregister_usb_gadget($?)} -> ERROR("linux:usb:gadget::double usb gadget deregistration");


STATE USEALL G1_C0_H0 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G1_C0_H0;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0}
    ERROR ("linux:usb:gadget::class registration with usb gadget");

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) == 0}
    ERROR("linux:usb:gadget::class registration with usb gadget");
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) <  0} GOTO G1_C0_H0;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) >  0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} ->
    ERROR("linux:usb:gadget::class deregistration with usb gadget");

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G1_C0_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G1_C0_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0}
    ERROR("linux:usb:gadget::class deregistration with usb gadget");

  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G1_C0_H0;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) != 0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) != 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) == 0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1)==0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) < 0} GOTO G1_C0_H0;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) > 0} GOTO Stop;

  MATCH CALL {ldv_unregister_chrdev_region($?)} -> ERROR("linux:usb:gadget::chrdev deregistration with usb gadget");

  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> ASSUME {((int)$1)==0} ERROR("linux:usb:gadget::double usb gadget registration");
  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> ASSUME {((int)$1)!=0} GOTO G1_C0_H0;
  MATCH CALL {ldv_unregister_usb_gadget($?)} -> GOTO G0_C0_H0;

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:usb:gadget::usb gadget registered at exit");


STATE USEALL G1_C1_H0 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G1_C1_H0;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0}
    ERROR ("linux:usb:gadget::class registration with usb gadget");

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1)==0}
    ERROR("linux:usb:gadget::class registration with usb gadget");
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) < 0} GOTO G1_C1_H0;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) > 0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} ->
    ERROR("linux:usb:gadget::class deregistration with usb gadget");

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G1_C1_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G1_C1_H0;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0}
    ERROR("linux:usb:gadget::class deregistration with usb gadget");

  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G1_C1_H0;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) != 0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) != 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) == 0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1)==0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) < 0} GOTO G1_C1_H0;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) > 0} GOTO Stop;

  MATCH CALL {ldv_unregister_chrdev_region($?)} -> ERROR("linux:usb:gadget::chrdev deregistration with usb gadget");

  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> ASSUME {((int)$1)==0} ERROR("linux:usb:gadget::double usb gadget registration");
  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> ASSUME {((int)$1)!=0} GOTO G1_C1_H0;
  MATCH CALL {ldv_unregister_usb_gadget($?)} -> GOTO G0_C1_H0;

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:usb:gadget::usb gadget registered at exit");


STATE USEALL G1_C0_H1 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G1_C0_H1;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0}
    ERROR ("linux:usb:gadget::class registration with usb gadget");

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1)==0}
    ERROR("linux:usb:gadget::class registration with usb gadget");
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) < 0} GOTO G1_C0_H1;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) > 0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} ->
    ERROR("linux:usb:gadget::class deregistration with usb gadget");

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G1_C0_H1;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G1_C0_H1;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0}
    ERROR("linux:usb:gadget::class deregistration with usb gadget");

  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G1_C0_H1;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) != 0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) != 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) == 0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1)==0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) < 0} GOTO G1_C0_H1;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) > 0} GOTO Stop;

  MATCH CALL {ldv_unregister_chrdev_region($?)} -> ERROR("linux:usb:gadget::chrdev deregistration with usb gadget");

  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> ASSUME {((int)$1)==0} ERROR("linux:usb:gadget::double usb gadget registration");
  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> ASSUME {((int)$1)!=0} GOTO G1_C0_H1;
  MATCH CALL {ldv_unregister_usb_gadget($?)} -> GOTO G0_C0_H1;

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:usb:gadget::usb gadget registered at exit");


STATE USEALL G1_C1_H1 :
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((void *)$1) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G1_C1_H1;
  MATCH RETURN {$1=ldv_create_class($?)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0}
    ERROR ("linux:usb:gadget::class registration with usb gadget");

  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1)==0}
    ERROR("linux:usb:gadget::class registration with usb gadget");
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) < 0} GOTO G1_C1_H1;
  MATCH RETURN {$1=ldv_register_class($?)} -> ASSUME {((int)$1) > 0} GOTO Stop;

  MATCH CALL {ldv_unregister_class($?)} ->
    ERROR("linux:usb:gadget::class deregistration with usb gadget");

  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((void *)$1) == 0} GOTO G1_C1_H1;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) > 2012} GOTO G1_C1_H1;
  MATCH CALL {ldv_destroy_class($1)} -> ASSUME {((unsigned long)$1) <= 2012; ((unsigned long)$1) > 0}
    ERROR("linux:usb:gadget::class deregistration with usb gadget");

  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) < 0} GOTO G1_C1_H1;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) != 0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) == 0; ((int)$2) == 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) != 0} GOTO Stop;
  MATCH RETURN {$1=ldv_register_chrdev($2)} -> ASSUME {((int)$1) >  0; ((int)$2) == 0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");

  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1)==0} ERROR("linux:usb:gadget::chrdev registration with usb gadget");
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) < 0} GOTO G1_C1_H1;
  MATCH RETURN {$1=ldv_register_chrdev_region($?)} -> ASSUME {((int)$1) > 0} GOTO Stop;

  MATCH CALL {ldv_unregister_chrdev_region($?)} -> ERROR("linux:usb:gadget::chrdev deregistration with usb gadget");

  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> ASSUME {((int)$1)==0} ERROR("linux:usb:gadget::double usb gadget registration");
  MATCH RETURN {$1=ldv_register_usb_gadget($?)} -> ASSUME {((int)$1)!=0} GOTO G1_C1_H1;
  MATCH CALL {ldv_unregister_usb_gadget($?)} -> GOTO G0_C1_H1;

  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:usb:gadget::usb gadget registered at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON
