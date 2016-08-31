OBSERVER AUTOMATON linux_iomem
INITIAL STATE Init;

STATE USEALL Init :
  MATCH ENTRY -> ENCODE {int iomem_state = 0;} GOTO Init;
  MATCH RETURN {$1=ldv_io_mem_remap($?)} -> ASSUME {((void *)$1) != 0} ENCODE {iomem_state=iomem_state+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_io_mem_remap($?)} -> ASSUME {((void *)$1) == 0} GOTO Init;
  MATCH CALL {ldv_io_mem_unmap($?)} -> ERROR("linux:iomem::less initial decrement");

STATE USEALL Inc :
  MATCH RETURN {$1=ldv_io_mem_remap($?)} -> ASSUME {((void *)$1) != 0} ENCODE {iomem_state=iomem_state+1;} GOTO Inc;
  MATCH RETURN {$1=ldv_io_mem_remap($?)} -> ASSUME {((void *)$1) == 0} GOTO Inc;
  MATCH CALL {ldv_io_mem_unmap($?)} -> ASSUME {iomem_state >  1} ENCODE {iomem_state=iomem_state-1;} GOTO Inc;
  MATCH CALL {ldv_io_mem_unmap($?)} -> ASSUME {iomem_state <= 1} ENCODE {iomem_state=iomem_state-1;} GOTO Init;
  MATCH CALL {ldv_check_final_state($?)} -> ERROR("linux:iomem::more initial at exit");

STATE USEFIRST Stop :
  TRUE -> GOTO Stop;

END AUTOMATON