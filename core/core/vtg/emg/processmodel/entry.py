#
# Copyright (c) 2014-2015 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

from core.vtg.emg.common import get_necessary_conf_property, model_comment
from core.vtg.emg.common.signature import import_declaration
from core.vtg.emg.common.process import Dispatch, Receive, Condition
from core.vtg.emg.processmodel.abstractprocess import AbstractProcess


class EntryProcessGenerator:

    def __init__(self, logger, conf):
        self.__logger = logger
        self.__conf = conf
        self.__default_signals = dict()

    def entry_process(self, analysis):
        """
        Generate process from which model should start and additional generated processes like insmod scenario for
        Linux kernel modules.

        :return: entry Process object, list with additional Process objects
        """
        additional_processes = list()

        with_insmod = get_necessary_conf_property(self.__conf, 'generate insmod scenario')
        if with_insmod:
            self.__logger.info('Generate insmod scenario')
            insmod = self.__generate_insmod_process(analysis, with_insmod)
            additional_processes.append(insmod)
        self.__logger.info('Entry point scenario')
        entry_process = self.__generate_base_process(not with_insmod)

        return entry_process, additional_processes

    def add_default_dispatch(self, process, receive):
        """
        Get signal receive and plan generation of peer dispatch for it.

        :param process: Process object with receive.
        :param receive: Receive object.
        :return: True - dispatch can be generated, False - dispatch will not be generated.
        """
        def add_signal(p, s, r):
            if p.identifier not in self.__default_signals:
                self.__default_signals[p.identifier] = {'activation': list(), 'deactivation': list(), 'process': p}

            if r and s not in self.__default_signals[p.identifier]['activation']:
                self.__default_signals[p.identifier]['activation'].append(s)
            elif not r and s not in self.__default_signals[p.identifier]['deactivation']:
                self.__default_signals[p.identifier]['deactivation'].append(s)

        if receive.name in get_necessary_conf_property(self.__conf, 'add missing deactivation signals'):
            add_signal(process, receive, False)
            return True
        elif receive.name in get_necessary_conf_property(self.__conf, 'add missing activation signals'):
            add_signal(process, receive, True)
            return True
        else:
            return False

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

    def __generate_alias(self, process, name, file, int_retval=False):
        new_name = "ldv_emg_{}".format(name)
        code = [
            "{}(void)\n".format("int {}".format(new_name) if int_retval else "void {}".format(new_name)),
            "{\n",
            "\t{}();\n".format("return {}".format(name) if int_retval else name),
            "}\n"
        ]
        # Add definition
        process.add_definition(file, name, code)
        process.add_declaration('environment model', name,
                                'extern {} {}(void);\n'.format("int" if int_retval else "void", new_name))

        return new_name

    def __generate_insmod_process(self, analysis, default_dispatches=False):
        self.__logger.info("Generate artificial process description to call Init and Exit module functions 'insmod'")
        ep = AbstractProcess("insmod")
        ep.comment = "Initialize or exit module."
        ep.self_parallelism = False
        ep.identifier = 0

        # Add register
        insmod_register = Receive('insmod_register')
        insmod_register.replicative = True
        insmod_register.comment = 'Trigger module initialization.'
        insmod_register.parameters = []
        ep.actions[insmod_register.name] = insmod_register
        ep.process = '(!{}).'.format(insmod_register.name)

        if len(analysis.inits) == 0:
            raise RuntimeError('Module does not have Init function')

        # Generate init subprocess
        for filename, init_name in analysis.inits:
            new_name = self.__generate_alias(ep, init_name, filename, True)
            init_subprocess = Condition(init_name)
            init_subprocess.comment = 'Initialize the module after insmod with {!r} function.'.format(init_name)
            init_subprocess.statements = [
                model_comment('callback', init_name, {'call': "{}();".format(init_name)}),
                "%ret% = {}();".format(new_name),
                "%ret% = ldv_post_init(%ret%);"
            ]
            self.__logger.debug("Found init function {}".format(init_name))
            ep.actions[init_subprocess.name] = init_subprocess

        # Add ret label
        ep.add_label('ret', import_declaration("int label"))

        # Generate exit subprocess
        if len(analysis.exits) == 0:
            self.__logger.debug("There is no exit function found")
        else:
            for filename, exit_name in analysis.exits:
                new_name = self.__generate_alias(ep, exit_name, filename, False)
                exit_subprocess = Condition(exit_name)
                exit_subprocess.comment = 'Exit the module before its unloading with {!r} function.'.format(exit_name)
                exit_subprocess.statements = [
                    model_comment('callback', exit_name, {'call': "{}();".format(exit_name)}),
                    "{}();".format(new_name)
                ]
                self.__logger.debug("Found exit function {}".format(exit_name))
                ep.actions[exit_subprocess.name] = exit_subprocess

        # Generate conditions
        success = ep.add_condition('init_success', ["%ret% == 0"], [], "Module has been initialized.")
        ep.actions[success.name] = success
        # Generate else branch
        failed = ep.add_condition('init_failed', ["%ret% != 0"], [], "Failed to initialize the module.")
        ep.actions[failed.name] = failed

        # Add deregister
        insmod_deregister = Receive('insmod_deregister')
        insmod_deregister.comment = 'Trigger module exit.'
        insmod_deregister.parameters = []
        ep.actions[insmod_deregister.name] = insmod_deregister

        # Add subprocesses finally
        for i, pair in enumerate(analysis.inits):
            ep.process += "<{0}>.(<init_failed>.".format(pair[1])
            for j, pair2 in enumerate(analysis.exits[::-1]):
                if pair2[0] == pair[0]:
                    break
            j = 1
            for _, exit_name in analysis.exits[:j - 1:-1]:
                ep.process += "<{}>.".format(exit_name)
            ep.process += "({})|<init_success>.".format(insmod_deregister.name)

        # Add default dispatches
        if default_dispatches:
            expr = self.__generate_default_dispatches(ep)
            if expr:
                ep.process += "{}.".format(expr)

        for _, exit_name in analysis.exits:
            ep.process += "<{}>.".format(exit_name)
        ep.process += "({})".format(insmod_deregister.name)
        ep.process += ")" * len(analysis.inits)
        self.__logger.debug("Artificial process for invocation of Init and Exit module functions is generated")
        return ep

    def __generate_default_dispatches(self, process):

        def make_signal(sp, rp, ra, guard):
            # Change name
            signal_name = "default_{}_{}".format(ra.name, rp.identifier)
            rp.rename_action(ra.name, signal_name)

            # Deregister dispatch
            self.__logger.debug("Generate copy of receive {} and make dispatch from it".format(ra.name))
            new_dispatch = Dispatch(ra.name)

            # Remove parameters
            new_dispatch.parameters = []
            ra.parameters = []

            # Replace condition
            new_dispatch.condition = [guard]
            ra.condition = None

            sp.actions[new_dispatch.name] = new_dispatch
            return new_dispatch

        # Do not do anything if no signals for default registration available
        if len(self.__default_signals) == 0:
            return None

        # To nondeterministically register and deregister pairs of default dispatches let us insert artificial action
        statements = []
        for receiver in (self.__default_signals[p]['process'] for p in self.__default_signals):
            # Create new label and add it to label set
            name = 'reg_guard_{}'.format(receiver.identifier)
            process.add_label(name, "int a")
            label = "%{}%".format(name)

            # Add initialization
            statements.append("{} = ldv_undef_int();".format(label))

            # Save label name
            self.__default_signals[receiver.identifier]['guard'] = label
        default_reg_con = process.add_condition('nondet_reg', [], statements,
                                                "Do registration and deregistration nondeterministically.")

        activations = list()
        deactivations = list()
        for receiver in (self.__default_signals[n]['process'] for n in self.__default_signals):
            # Process activation signals
            for activation in self.__default_signals[receiver.identifier]['activation']:
                # Alloc memory after default registraton
                allocation_name = 'default_alloc_{}'.format(receiver.identifier)
                receiver.add_condition(allocation_name, [],
                                       ['{0} = $UALLOC({0});'.format(name) for name in activation.parameters],
                                       "Allocate memory after default registration.")
                receiver.insert_action(activation.name, '<{}>'.format(allocation_name), position='after')

                # Rename and make dispatch
                nd = make_signal(process, receiver, activation, self.__default_signals[receiver.identifier]['guard'])
                nd.comment = "Register {0!r} callbacks with unknown registration function."
                activations.append(nd)

            # process deactivation signals
            for deactivation in self.__default_signals[receiver.identifier]['deactivation']:
                # Free memory after default deregistraton if the memory was actually allocated by EMG
                if len(self.__default_signals[receiver.identifier]['activation']) > 0:
                    free_name = 'default_free_{}'.format(receiver.identifier)
                    receiver.add_condition(free_name, [],
                                           ['$FREE({0});'.format(name) for name in deactivation.parameters],
                                           "Free memory before default deregistration.")
                    receiver.insert_action(deactivation.name, '<{}>'.format(free_name), position='before')

                # Rename and make dispatch
                nd = make_signal(process, receiver, deactivation, self.__default_signals[receiver.identifier]['guard'])
                nd.comment = "Deregister {0!r} callbacks with unknown deregistration function."
                deactivations.append(nd)

        if len(activations + deactivations) == 0:
            expression = None
        else:
            activation_expr = ["[@{}]".format(a.name) for a in activations]
            deactivation_expr = ["[@{}]".format(a.name) for a in reversed(deactivations)]
            expression = "<{}>.{}".format(default_reg_con.name, ".".join(activation_expr + deactivation_expr))

        return expression

