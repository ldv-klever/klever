def __generate_base_process(self, default_dispatches=False):
    if get_conf_property(conf, "extra processes"):
        self.logger.info('Looking for a file with additional processes {!r}'.
                         format(get_necessary_conf_property(self.conf, "extra processes")))
        with open(core.utils.find_file_or_dir(self.logger,
                                              get_necessary_conf_property(self.conf, "main working directory"),
                                              get_necessary_conf_property(self.conf, "extra processes")),
                  encoding='utf8') as fp:
            extra_processes = json.load(fp)

        # Merge manually prepared processes with generated ones and provide the model to modelTranslator
        # todo: how to replace main process
        if extra_processes:
            for category in extra_processes:
                generated_processes[category].update(extra_processes[category])

        # Parse this final model
        model_processes, env_processes, entry_process = \
            parse_event_specification(emg.logger,
                                      get_necessary_conf_property(emg.conf, 'intermediate model options'),
                                      generated_processes, abstract=False)

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