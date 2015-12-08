import re

from psi.avtg.emg.interfaces import Interface, Signature


class EventModel:

    def __init__(self, logger, analysis, events):
        return


class EventSpecification:
    raw = {}
    funсtions = {}
    processes = {}

    def __init__(self, logger, raw_spec):
        self.raw = raw_spec
        self.logger = logger

        # Import kernel models
        self.logger.info("Import functions and macro-functions models")
        self.__import_models()

        # Import other processes
        self.logger.info("Import functions and macro-functions models")
        self.__import_processes()

    def __import_models(self):
        if "kernel model" in self.raw:
            for name_list in self.raw["kernel model"]:
                names = name_list.split(", ")
                for name in names:
                    # TODO: fix name
                    process = Process(name_list, self.raw["kernel model"][name_list])
                    self.funсtions[name] = process

    def __import_processes(self):
        pass


class Label:
    def __init__(self, name):
        self.container = False
        self.resource = False
        self.callback = False
        self.parameter = False
        self.parameters = []

        self.value = None
        self.signature = None
        self.interface = None
        self.name = name

    def _import_json(self, dic):
        for att in ["container", "resource", "callback", "parameter"]:
            if att in dic:
                setattr(self, att, dic[att])

        if "value" in dic:
            self.value = dic["value"]

        if "interface" in dic:
            self.interface = dic["interface"]

        if "signature" in dic:
            self.signature = Signature(dic["signature"])


class Process:

    def __init__(self, name, dic={}):
        # Default values
        self.process = None
        self.labels = {}
        self.subprocesses = {}

        self.type = "process"
        self.name = name
        self._import_dictionary(dic)

    def _parse_process(self, root, expression):
        pass

    def _import_dictionary(self, dic):
        # Import labels
        if "labels" in dic:
            for name in dic["labels"]:
                label = Label(name)
                label._import_json(dic["labels"][name])
                self.labels[name] = label

        # Import subprocesses
        if "subprocesses" in dic:
            for name in dic["subprocesses"]:
                subprocess = Subprocess(name, dic["subprocesses"][name])
                self.subprocesses[name] = subprocess

        # Import process
        if "process" in dic:
            self.process = dic["process"]

        if "parameters" in dic:
            self.parameters = dic["parameters"]

        if self.type and self.type == "process" and len(self.subprocesses.keys()) > 0:
            self.__determine_subprocess_types()

    def __determine_subprocess_types(self):
        dispatch_template = "\[{}(?:\(\d+\))?\]"
        receive_template = "\(!?{}(?:\(\d+\))?\)"
        subprocess_template = "{}(?:\(\d+\))?"

        processes = [self.subprocesses[process_name].process for process_name in self.subprocesses
                     if self.subprocesses[process_name].process]
        processes.append(self.process)

        for subprocess_name in self.subprocesses:
            subprocess_re = re.compile("\{" + subprocess_template.format(subprocess_name) + "\}")
            receive_re = re.compile(receive_template.format(subprocess_name))
            dispatch_re = re.compile(dispatch_template.format(subprocess_name))
            regexes = [
                {"regex": subprocess_re, "type": "subprocess"},
                {"regex": dispatch_re, "type": "dispatch"},
                {"regex": receive_re, "type": "receive"}
            ]

            match = 0
            process_type = None
            for regex in regexes:
                for process in processes:
                    if regex["regex"].search(process):
                        match += 1
                        process_type = regex["type"]
                        break

            if match == 0:
                raise KeyError("Subprocess {} from process {} is not used actually".format(subprocess_name, self.name))
            elif match > 1:
                raise KeyError("Subprocess {} from process {} was used in different actions but it can be dispatch, "
                               "receive or subprocess at once".format(subprocess_name, self.name))
            else:
                self.subprocesses[subprocess_name].type = process_type


class Subprocess(Process):

    def __init__(self, name, dic={}):
        self.type = None
        self.name = name
        self.process = None
        self._import_dictionary(dic)

    def _import_dictionary(self, dic):
        super()._import_dictionary(dic)
        self.labels = {}
        self.subprocesses = {}
        return

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
