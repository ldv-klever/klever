OBSERVER AUTOMATON linux_bitops
INITIAL STATE Init;

STATE USEALL Init :
  MATCH RETURN {$3=ldv_find_next_bit($1,$2)} -> ASSUME {((unsigned long)$2) >  ((unsigned long)$1)} ERROR("linux:bitops::offset out of range");
  MATCH RETURN {$3=ldv_find_next_bit($1,$2)} -> ASSUME {((unsigned long)$2) <= ((unsigned long)$1);((unsigned long)$3) <= ((unsigned long)$1)} GOTO Init;
  MATCH RETURN {$3=ldv_find_next_bit($1,$2)} -> ASSUME {((unsigned long)$2) <= ((unsigned long)$1);((unsigned long)$3) >  ((unsigned long)$1)} GOTO Stop;

  MATCH RETURN {$2=ldv_find_first_bit($1)} -> ASSUME {((unsigned long)$2) <= ((unsigned long)$1)} GOTO Init;
  MATCH RETURN {$2=ldv_find_first_bit($1)} -> ASSUME {((unsigned long)$2) >  ((unsigned long)$1)} GOTO Stop;


STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON