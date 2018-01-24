def __generate_base_process(self, default_dispatches=False):
    self.__logger.debug("Generate main process")
    ep = AbstractProcess("main")
    ep.comment = "Main entry point function."
    ep.self_parallelism = False
    ep.category = "main"
    ep.identifier = 0

    # Add register
    init = ep.add_condition('init', [], ["ldv_initialize();"], "Initialize rule models.")
    ep.process = '({}).'.format(init.name)

    # Add default dispatches
    if default_dispatches:
        # todo: insert there registration of initially present processes
        expr = self.__generate_default_dispatches(ep)
        if expr:
            ep.process += "{}.".format(expr)
    else:
        # Add insmod signals
        regd = Dispatch('insmod_register')
        regd.comment = 'Start environment model scenarios.'
        ep.actions[regd.name] = regd
        derd = Dispatch('insmod_deregister')
        derd.comment = 'Stop environment model scenarios.'
        ep.actions[derd.name] = derd
        ep.process += "[{}].[{}]".format(regd.name, derd.name)

    # Generate final
    final = ep.add_condition('final', [], ["ldv_check_final_state();", "ldv_assume(0);"],
                             "Check rule model state at the exit.")
    ep.process += '.<{}>'.format(final.name)

    self.__logger.debug("Main process is generated")
    return ep