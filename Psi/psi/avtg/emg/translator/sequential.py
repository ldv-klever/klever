import copy

from psi.avtg.emg.translator import AbstractTranslator
from psi.avtg.emg.interfaces import Signature


class Translator(AbstractTranslator):
    unmatched_constant = 2
    automata = []

    def _generate_entry_point(self):

        ri = {}
        for process in self.model["models"] + self.model["processes"]:
            ri[process.identifier] = process.collect_relevant_interfaces()

        # Generate automatas
        self.automata = []
        for process in self.model["processes"]:
            if len(ri[process.identifier]["callbacks"]) > 0:
                self.automata.extend(self.__generate_automata(ri[process.identifier], process))
            else:
                self.automata.append(Automata(self.logger, len(self.automata), self.entry_file, process))

        return

    def __generate_automata(self, ri, process):
        ri["implementations"] = {}
        process_automata = []

        # Set containers
        for callback in ri["callbacks"]:
            if type(process.labels[callback[0]].interface) is list:
                interfaces = process.labels[callback[0]].interface
            else:
                interfaces = [process.labels[callback[0]].interface]
            for interface in interfaces:
                intfs = self.__get_interfaces(process, interface, callback)
                for index in range(len(intfs)):
                    ri["implementations"][intfs[index].full_identifier] = \
                        self.__get_implementations(intfs[index].full_identifier)

        # Set resources
        for resource in ri["resources"]:
            ri["implementations"][resource.interface] = self.__get_implementations(resource.interface)

        # Copy processes
        labels = [process.labels[name] for name in process.labels if process.labels[name].container
                  and process.labels[name].interface
                  and process.labels[name].interface in ri["implementations"]
                  and ri["implementations"][process.labels[name].interface]]
        if len(labels) == 0:
            for index in range(self.unmatched_constant):
                au = Automata(self.logger, len(self.automata) + len(process_automata), self.entry_file, process)
                au.label_map = ri
                process_automata.append(au)
        else:
            summ = []
            au = Automata(self.logger, len(self.automata), self.entry_file, process)
            au.label_map = ri
            summ.append(au)

            for label in [process.labels[name] for name in process.labels if process.labels[name].container
                          and process.labels[name] not in labels]:
                new = []
                new.extend(summ)
                for au in summ:
                    cp = copy.copy(au)
                    cp.identifier = len(self.automata) + len(new)
                    new.extend(cp)
                summ.extend(new)
            process_automata.extend(summ)

        return process_automata

    def __get_implementations(self, identifier):
        retval = []
        if self.analysis.interfaces[identifier].signature.type_class == "struct" \
                and self.analysis.interfaces[identifier].implementations:
            for file in self.analysis.interfaces[identifier].implementations:
                for variable in self.analysis.interfaces[identifier].implementations[file]:
                    retval.append([file, variable])
        elif self.analysis.interfaces[identifier].signature.type_class == "function":
            category = self.analysis.interfaces[identifier].category
            interface = self.analysis.interfaces[identifier]
            for container in [self.analysis.categories[category]["containers"][name] for name in
                              self.analysis.categories[category]["containers"]
                              if self.analysis.categories[category]["containers"][name].implementations and
                              interface.identifier in
                                              self.analysis.categories[category]["containers"][name].fields.values()]:
                field = list(container.fields.keys())[list(container.fields.values()).index(interface.identifier)]
                for path in container.implementations:
                    for variable in container.implementations[path]:
                        if field in self.analysis.implementations[path][variable]:
                            retval.append(self.analysis.implementations[path][variable][field])

        if len(retval) == 0:
            return None
        else:
            return retval

    def __get_interfaces(self, process, interface, access):
        ret = [self.analysis.interfaces[interface]]
        for index in range(1, len(access)):
            category = ret[-1].category
            identifier = ret[-1].fields[access[index]]
            identifier = "{}.{}".format(category, identifier)
            ret.append(self.analysis.interfaces[identifier])
        return ret


class Automata:

    def __init__(self, logger, identifier, file, process):
        self.logger = logger
        self.identifier = identifier
        self.file = file
        self.process = process
        self.label_map = {}
        self.subprocess_map = {}
        self.automata = {}
        self.state_variable = {}



__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'