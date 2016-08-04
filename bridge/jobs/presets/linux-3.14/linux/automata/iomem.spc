OBSERVER AUTOMATON linux_iomem
INITIAL STATE Init;

STATE USEALL Init :
  MATCH ENTRY -> ENCODE {int iomem = 0;} GOTO Init;
  MATCH RETURN {$1=ldv_io_mem_remap($?)} -> ASSUME {((void *)$1) != 0} ENCODE {iomem=iomem+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_io_mem_remap($?)} -> ASSUME {((void *)$1) == 0} GOTO Init;
  MATCH CALL {ldv_io_mem_unmap($?)} -> ERROR("linux:iomem::less initial decrement");

STATE USEALL Inc :
  MATCH RETURN {$1=ldv_io_mem_remap($?)} -> ASSUME {((void *)$1) != 0} ENCODE {iomem=iomem+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_io_mem_remap($?)} -> ASSUME {((void *)$1) == 0} GOTO Inc;
  MATCH CALL {ldv_io_mem_unmap($?)} -> ASSUME {iomem >  1} ENCODE {iomem=iomem-1;} GOTO Inc;
  MATCH CALL {ldv_io_mem_unmap($?)} -> ASSUME {iomem <= 1} ENCODE {iomem=iomem-1;} GOTO Init;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:iomem::more initial at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON