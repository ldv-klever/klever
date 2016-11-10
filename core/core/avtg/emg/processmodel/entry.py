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

        with_insmod = get_necessary_conf_property('generate insmod scenario')
        if with_insmod:
            self.__logger.info('Generate insmod scenario')
            insmod = self.__generate_insmod_process(analysis, not with_insmod)
            additional_processes.append(insmod)
        self.__logger.info('Entry point scenario')
        entry_process = self.__generate_base_process(with_insmod)

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
        init = ep.add_condition('init', [], ["ldv_initialize();"], "Begin main scenario")
        self.entry_process.process = '({})'.format(init.name)

        # Add default dispatches
        if default_dispatches:
            expr = self.__generate_default_dispatches(ep)
            self.entry_process.process += expr

        # Generate final
        final = ep.add_condition('final', [], ["ldv_check_final_state();", "ldv_stop();"], "Finish main scenario")
        self.entry_process.process += '.<{}>'.format(final.name)

        self.__logger.debug("Main process is generated")

    def __generate_insmod_process(self, analysis, default_dispatches=False):
        self.__logger.info("Generate artificial process description to call Init and Exit module functions 'insmod'")
        ep = Process("insmod")
        ep.category = "entry"
        ep.identifier = 0
        ep = ep

        # Add register
        insmod_register = Receive('insmod_register')
        insmod_register.parameters = []
        ep.actions[insmod_register.name] = insmod_register
        self.entry_process.process = '({})'.format(insmod_register.name)

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

        # Add subprocesses finally
        ep.process = ""
        for i, pair in enumerate(analysis.inits):
            ep.process += "[{0}].(<init_failed>.".format(pair[1])
            for j, pair2 in enumerate(analysis.exits[::-1]):
                if pair2[0] == pair[0]:
                    break
            j = 1
            for _, exit_name in analysis.exits[:j - 1:-1]:
                ep.process += "[{}].".format(exit_name)
            ep.process += "<stop>|<init_success>."

        # Add default dispatches
        if default_dispatches:
            expr = self.__generate_default_dispatches(ep)
            ep.process += "{}.".format(expr)
                    
        # Add deregister
        insmod_deregister = Dispatch('insmod_deregister')
        insmod_deregister.parameters = []
        ep.actions[insmod_deregister.name] = insmod_deregister

        for _, exit_name in analysis.exits:
            ep.process += "[{}].".format(exit_name)
        ep.process += "[{}]".format(insmod_deregister.name)
        ep.process += ")" * len(analysis.inits)
        self.__logger.debug("Artificial process for invocation of Init and Exit module functions is generated")

    def __generate_default_dispatches(self, process):

        def make_signal(prs, rp, ra):
            # Add parameters to alloc memory
            prs.update(ra.parameters)
            # Change signal name
            # Generate artificial dispatch action
            # Add generated action to the entry pocess
            return None

        for receiver in (p['process'] for p in self.__default_signals):
            labels_to_init = set()
            activations = list()
            deactivations = list()

            # Process activation signals
            for activation in self.__default_signals[receiver.name]['activation']:
                nd = make_signal(labels_to_init, receiver, activation)
                activations.append(nd)
            # process deactivation signals
            for deactivation in self.__default_signals[receiver.name]['deactivation']:
                nd = make_signal(labels_to_init, receiver, deactivation)
                deactivations.append(nd)

            # Generate alloc action
            process.add_condition('default_alloc', [], [],
                                  "Alloc memory to perform registration of callbacks for which an activation event is "
                                  "undetermined.")

            # Generate free action

            # Generate expression


            # Change name
            new_subprocess_name = "{}_{}_{}".format(receive.name, process.name, process.identifier)
            rename_subprocess(process, receive.name, new_subprocess_name)

            # Deregister dispatch
            self.logger.debug("Generate copy of receive {} and make dispatch from it".format(receive.name))
            new_dispatch = Dispatch(receive.name)

            # Peer these subprocesses
            new_dispatch.peers.append(
                {
                    "process": process,
                    "subprocess": process.actions[new_dispatch.name]
                })
            process.actions[new_dispatch.name].peers.append(
                {
                    "process": self.entry_process,
                    "subprocess": new_dispatch
                })

            self.logger.debug("Save dispatch {!r} to be default".format(new_dispatch.name))

            # todo: implement it taking into account that each parameter may have sevaral implementations
            # todo: relevant to issue #6566
            # Add labels if necessary
            # for index in range(len(new_dispatch.parameters)):
            #    parameter = new_dispatch.parameters[index]
            #
            #    # Get label
            #    label, tail = process.extract_label_with_tail(parameter)
            #
            #    # Copy label to add to dispatcher process
            #    new_label_name = "{}_{}_{}".format(process.name, label.name, process.identifier)
            #    if new_label_name not in self.entry_process.labels:
            #        new_label = copy.deepcopy(label)
            #        new_label.name = new_label_name
            #        self.logger.debug("To process {} add new label {}".format(self.entry_process.name, new_label_name))
            #        self.entry_process.labels[new_label.name] = new_label
            #    else:
            #        self.logger.debug("Process {} already has label {}".format(self.entry_process.name, new_label_name))
            #
            #    # Replace parameter
            #    new_dispatch.parameters[index] = parameter.replace(label.name, new_label_name)
            new_dispatch.parameters = []
            receive.parameters = []

            # Replace condition
            # todo: do this according to parameters (relevant to issue #6566)
            new_dispatch.condition = None
            receive.condition = None

            new_dispatch.comment = "Deregister {0!r} callbacks with unknown deregistration function."
            new_dispatch.comment = "Register {0!r} callbacks with unknown registration function."

            # All default registrations and then deregistrations
            names = [name for name in sorted(self.entry_process.actions.keys())
                     if type(self.entry_process.actions[name]) is Dispatch]
            for name in names:
                self.entry_process.actions[name].broadcast = True
            names.sort()
            names.reverse()
            names[len(names):] = reversed(names[len(names):])
            dispatches.extend(["[@{}]".format(name) for name in names])

            none = Condition('none')
            none.comment = 'Skip registration of callbacks for which registration and deregistration methods has not been ' \
                           'found.'
            none.type = "condition"
            self.entry_process.actions['none'] = none

            return [new_dispatch.name, new_dispatch]

