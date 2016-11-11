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

from core.avtg.emg.common import get_necessary_conf_property
from core.avtg.emg.common.signature import import_declaration
from core.avtg.emg.common.process import Condition, Dispatch, Receive, Call, Label, Process


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
            if p.name not in self.__default_signals:
                self.__default_signals[p.name] = {'activation': list(), 'deactivation': list(), 'process': p}
                if r:
                    self.__default_signals[p.name]['activation'].append(s)
                else:
                    self.__default_signals[p.name]['deactivation'].append(s)

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
        ep = Process("main")
        ep.category = "main"
        ep.identifier = 0

        # Add register
        init = ep.add_condition('init', [], ["ldv_initialize();"], "Initialize rule models.")
        ep.process = '({}).'.format(init.name)

        # Add default dispatches
        if default_dispatches:
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
        final = ep.add_condition('final', [], ["ldv_check_final_state();", "ldv_stop();"],
                                 "Check rule model state at the exit.")
        ep.process += '.<{}>'.format(final.name)

        self.__logger.debug("Main process is generated")
        return ep

    def __generate_insmod_process(self, analysis, default_dispatches=False):
        self.__logger.info("Generate artificial process description to call Init and Exit module functions 'insmod'")
        ep = Process("insmod")
        ep.category = "entry"
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
            init_label = Label(init_name)
            init_label.value = "& {}".format(init_name)
            init_label.prior_signature = import_declaration("int (*f)(void)")
            init_label.file = filename
            init_subprocess = Call(init_label.name)
            init_subprocess.comment = 'Initialize the module after insmod with {!r} function.'.format(init_name)
            init_subprocess.callback = "%{}%".format(init_label.name)
            init_subprocess.retlabel = "%ret%"
            init_subprocess.post_call = [
                '%ret% = ldv_post_init(%ret%);'
            ]
            self.__logger.debug("Found init function {}".format(init_name))
            ep.labels[init_label.name] = init_label
            ep.actions[init_label.name] = init_subprocess

        ret_label = Label('ret')
        ret_label.prior_signature = import_declaration("int label")
        ep.labels[ret_label.name] = ret_label

        # Generate exit subprocess
        if len(analysis.exits) == 0:
            self.__logger.debug("There is no exit function found")
            exit_subprocess = Call('exit')
            exit_subprocess.callback = "%exit%"

            exit_label = Label('exit')
            exit_label.prior_signature = import_declaration("void (*f)(void)")
            exit_label.value = None
            exit_label.file = None
            ep.labels['exit'] = exit_label
            ep.actions[exit_subprocess.name] = exit_subprocess
        else:
            for filename, exit_name in analysis.exits:
                exit_label = Label(exit_name)
                exit_label.prior_signature = import_declaration("void (*f)(void)")
                exit_label.value = "& {}".format(exit_name)
                exit_label.file = filename
                exit_subprocess = Call(exit_label.name)
                exit_subprocess.comment = 'Exit the module before its unloading with {!r} function.'.format(exit_name)
                exit_subprocess.callback = "%{}%".format(exit_label.name)
                self.__logger.debug("Found exit function {}".format(exit_name))
                ep.labels[exit_label.name] = exit_label
                ep.actions[exit_label.name] = exit_subprocess

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
            ep.process += "[{0}].(<init_failed>.".format(pair[1])
            for j, pair2 in enumerate(analysis.exits[::-1]):
                if pair2[0] == pair[0]:
                    break
            j = 1
            for _, exit_name in analysis.exits[:j - 1:-1]:
                ep.process += "[{}].".format(exit_name)
            ep.process += "({})|<init_success>.".format(insmod_deregister.name)

        # Add default dispatches
        if default_dispatches:
            expr = self.__generate_default_dispatches(ep)
            if expr:
                ep.process += "{}.".format(expr)

        for _, exit_name in analysis.exits:
            ep.process += "[{}].".format(exit_name)
        ep.process += "({})".format(insmod_deregister.name)
        ep.process += ")" * len(analysis.inits)
        self.__logger.debug("Artificial process for invocation of Init and Exit module functions is generated")
        return ep

    def __generate_default_dispatches(self, process):

        def make_signal(sp, rp, ra):
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
            new_dispatch.condition = None
            ra.condition = None

            sp.actions[new_dispatch.name] = new_dispatch
            return new_dispatch

        activations = list()
        deactivations = list()
        for receiver in (self.__default_signals[n]['process'] for n in self.__default_signals):
            # Process activation signals
            for activation in self.__default_signals[receiver.name]['activation']:
                # Alloc memory after default registraton
                allocation_name = 'default_alloc_{}'.format(receiver.identifier)
                receiver.add_condition(allocation_name, [],
                                       ['{0} = $UALLOC({0});'.format(name) for name in activation.parameters],
                                       "Alloc memory after default registration.")
                receiver.insert_action(activation.name, after='<{}>'.format(allocation_name))

                # Rename and make dispatch
                nd = make_signal(process, receiver, activation)
                nd.comment = "Register {0!r} callbacks with unknown registration function."
                activations.append(nd)

            # process deactivation signals
            for deactivation in self.__default_signals[receiver.name]['deactivation']:
                # Free memory after default deregistraton
                free_name = 'default_free_{}'.format(receiver.identifier)
                receiver.add_condition(free_name, [],
                                       ['$FREE({0});'.format(name) for name in deactivation.parameters],
                                       "Free memory before default deregistration.")
                receiver.insert_action(deactivation.name, before='<{}>'.format(free_name))

                nd = make_signal(process, receiver, deactivation)
                nd.comment = "Deregister {0!r} callbacks with unknown deregistration function."
                deactivations.append(nd)

        if len(activations + deactivations) == 0:
            expression = None
        else:
            process.add_condition('none', [], [], 'Skip default callbacks registrations and deregistrations.')
            activation_expr = ["[@{}]".format(a.name) for a in activations]
            deactivation_expr = ["[@{}]".format(a.name) for a in reversed(deactivations)]
            expression = "({} | <none>)".format(".".join(activation_expr + deactivation_expr))

        return expression

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'

