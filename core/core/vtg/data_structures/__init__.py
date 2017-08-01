#!/usr/bin/python3

import json
import re
import os
import shutil
import glob
import tarfile

import core.utils


from xml.etree import ElementTree
from xml.dom import minidom

UNKNOWN = "unknown"
SAFE = "safe"
UNSAFE = "unsafe"
C_FILE = "C file"
AUTOMATON = "automaton"
PENDING = "PENDING"
PROPERTIES_SEPARATOR = ";"
CIL_FILE = "cil.i"
ASSERTIONS_MAP_FILE = "assertions_map.c"


class Model(object):
    """
    Representation of one model (rule specification).
    """

    def __init__(self, name: str, sources: {}, assertions: []):
        self.name = name  # unique id
        self.sources = sources  # map model type -> file with model
        self.assertions = assertions  # list of checked assertions


class Specification(object):
    """
    Representation of specification (several models) to be checked.
    """

    def __init__(self, separate_assertions=False, core_model=C_FILE):
        self.__specification = list()  # list of Models
        self.__separate_assertions = separate_assertions  # Check each assertion separately if this is True.
        self.__model = core_model  # Type of model, which is used in verification task.

    def delete_model(self, target_assertion):
        """
        Remove assertions from models.
        :param target_assertion: list of assertions.
        """
        for model in self.__specification:
            if self.__separate_assertions:
                for assertion in model.assertions:
                    if assertion == target_assertion:
                        model.assertions.remove(assertion)
                        break
            else:
                if model.name == target_assertion:
                    self.__specification.remove(model)
                    break

    def add_model(self, sources: {}, assertions: []):
        """
        Add new model in specification.
        :param sources:
        :param assertions:
        """
        name = self.__get_common_assertion(assertions)
        model = Model(name, sources, assertions)
        self.__specification.append(model)

    def get_assertions(self) -> []:
        """
        Returns all assertions to be checked.
        :return: all assertions of all models in case of __separate_assertions or all model names otherwise.
        """
        result = []
        for model in self.__specification:
            if self.__separate_assertions:
                for assertion in model.assertions:
                    result.append(assertion)
            else:
                result.append(model.name)
        return result

    def update_separate_assertions(self, separate_assertions):
        self.__separate_assertions = separate_assertions

    def update_model(self, core_model) -> str:
        if core_model:
            self.__model = core_model
        return self.__model

    def get_source_files(self, target_assertions: []) -> []:
        """
        Return all model files to be passed to the verifier.
        :param target_assertions:
        :return: list of model source files.
        """
        result = set()
        for model in self.__specification:
            if self.__model in model.sources:
                if self.__separate_assertions:
                    for assertion in model.assertions:
                        if assertion in target_assertions:
                            result.add(model.sources[self.__model])
                else:
                    if model.name in target_assertions:
                        result.add(model.sources[self.__model])
        return list(result)

    def generate_assertions_map(self, target_assertions: [], united_assertion=None, error_function=None) -> str:
        """
        Generate file, which binds checked assertions to error locations in source code.
        :param target_assertions: assertions, for which file is generated.
        :param united_assertion: use one specified assertion name for all assertions.
        :param error_function: use specified error function name rather than taken from configuration.
        :return: generated file.
        """
        with open(ASSERTIONS_MAP_FILE, 'w') as fp:
            for model in self.__specification:
                if self.__model in model.sources:
                    if self.__separate_assertions:
                        for assertion in model.assertions:
                            if assertion in target_assertions:
                                fp.write(self.__get_assert_repr(united_assertion or assertion, assertion,
                                                                error_function))
                    else:
                        if model.name in target_assertions:
                            for assertion in model.assertions:
                                fp.write(self.__get_assert_repr(united_assertion or model.name, assertion,
                                                                error_function))
        return ASSERTIONS_MAP_FILE

    def __get_assert_repr(self, common_assertion, assertion, specific_error_function=None):
        if specific_error_function:
            error_function = specific_error_function
        else:
            error_function = "__VERIFIER_error_{0}".format(re.sub(r'\W', '_', common_assertion))
        return 'void {0}(void);\n'.format(error_function) + \
               'void ldv_assert_{1}(int expr) {{\n\tif (!expr)\n\t\t{0}();\n}}\n'.format(error_function,
                                                                                         re.sub(r'\W', '_', assertion))

    def copy_models(self, target_assertions: [], united_assertion=None):
        """
        Copy model source files, which are not passed to verifier directly.
        :param target_assertions: assertions, for which file is generated.
        :param united_assertion: use one specified assertion name for all assertions.
        """
        if united_assertion:
            with open(united_assertion + ".spc", 'w', encoding='ascii') as fp_out:
                for model in self.__specification:
                    if self.__model in model.sources:
                        if model.name in target_assertions:
                            with open(model.sources[self.__model]) as fp_in:
                                fp_out.write(fp_in.read() + '\n')
        else:
            counter = 0
            for model in self.__specification:
                if self.__model in model.sources:
                    if self.__separate_assertions:
                        for assertion in model.assertions:
                            original_automaton = model.sources[self.__model]
                            if assertion in target_assertions:
                                new_automaton = assertion + ".spc"
                                with open(new_automaton, 'w', encoding='ascii') as fp_out, \
                                        open(original_automaton) as fp_in:
                                    internal_var = None
                                    current_state = None
                                    for line in fp_in:

                                        # Make automaton variables names unique.
                                        if not internal_var:
                                            res = re.search(r'ENTRY(\s+)->(\s+)ENCODE(\s+)\{(\w+)(\s+)(\w+)(.*)\}',
                                                            line)
                                            if res:
                                                internal_var = res.group(6)
                                        if internal_var:
                                            line = re.sub(internal_var, '{0}_{1}'.format(internal_var, counter), line)

                                        # Make automaton name unique.
                                        res = re.search(r'OBSERVER AUTOMATON (.+)', line)
                                        if res:
                                            old_name = res.group(1)
                                            new_name = old_name + '_' + '{0}'.format(counter)
                                            counter += 1
                                            line = re.sub(old_name, new_name, line)

                                        # Get current state name.
                                        res = re.search(r'STATE(\s+)(\w+)(\s+)(\w+)(\s*):', line)
                                        if res:
                                            current_state = res.group(4)

                                        # Here we go to the current state (i.e. do nothing) to ignore this assertion.
                                        res = re.search(r'ERROR\(\"(.+)\"\);', line)
                                        if res:
                                            current_assertion = res.group(1)

                                            if not current_assertion == assertion:
                                                line = re.sub(r'ERROR\(\"(.+)\"\);', 'GOTO {0};'.format(current_state),
                                                              line)

                                        fp_out.write('{0}'.format(line))
                    else:
                        if model.name in target_assertions:
                            original_automaton = model.sources[self.__model]
                            new_automaton = model.name + ".spc"
                            shutil.copy(original_automaton, new_automaton)

    def __get_common_assertion(self, assertions) -> str:
        # Here we assume, that all assertions names are presented in the following way:
        # <common_name>::<specific_name>
        # TODO: For general properties this may not be true.
        match = re.search(r'(.+)::(.*)', os.path.commonprefix(assertions))
        if match:
            return match.groups()[0]
        else:
            return ''


class Resources(object):
    """
    Represents resources usage or resource limitations.
    There are predefined resources (cpu time, wall time, memory), and additional resources.
    """

    def __init__(self, cpu_time=0, wall_time=0, memory_usage=0, additional={}):
        self.cpu_time = cpu_time  # in ms (integer)
        self.wall_time = wall_time  # in ms (integer)
        self.memory_usage = memory_usage  # in bytes
        self.additional = additional  # map resource name -> value

    def get_basic_representation(self):
        """
        :return: Returns basic representation of resources for reports.
        """
        result = {'CPU time': self.cpu_time,
                  'wall time': self.wall_time,
                  'memory size': self.memory_usage
                  }
        result.update(self.additional)
        return result

    def update(self, added_resources):
        """
        Increase consumed resources by specified amount.
        :param added_resources: Resources object, which is used to increase current values.
        """
        self.cpu_time += added_resources.cpu_time
        self.wall_time += added_resources.wall_time
        self.memory_usage = max(self.memory_usage, added_resources.memory_usage)
        for key, val in added_resources.additional.items():
            if key in self.additional:
                self.additional[key] += val
            else:
                self.additional[key] = val


class VerificationTask(object):
    """
    Representation of verification (reachability) task.
    """

    def __init__(self, name: str, sources: list, specification: Specification, tool_config: str, strategy,
                 resources: Resources):

        self.name = name  # name of checked verification object (e.g. module name)
        self.logger = strategy.logger
        self.config = VerificationConfig(tool_config, strategy.conf, specification, resources, name)

        self.__sources = sources  # list of paths to source files
        self.specification = specification

        if 'separate assertion' in self.config.strategy:
            self.__separate_assertions = self.config.strategy['separate assertion']
        else:
            self.__separate_assertions = False
        if 'model' in self.config.strategy:
            self.model = self.config.strategy['model']
        else:
            self.model = C_FILE

        self.__sanity_checks(strategy, tool_config)

        self.specification.update_model(self.model)

        self.__task_files = []  # files for verifier

    def update_config(self, tool_config: str, strategy, resources: Resources):
        """
        Change configuration for verification task.
        :param tool_config: New configuration name.
        :param strategy:
        :param resources: new resource limitations.
        """
        self.config = VerificationConfig(tool_config, strategy.conf, self.specification, resources, self.name)

        if 'separate assertion' in self.config.strategy:
            self.__separate_assertions = self.config.strategy['separate assertion']
        else:
            self.__separate_assertions = False
        if 'model' in self.config.strategy:
            self.model = self.config.strategy['model']
        else:
            self.model = C_FILE

        self.__sanity_checks(strategy, tool_config)

        self.specification.update_model(self.model)

        self.__task_files = []  # files for verifier

    def get_assertions(self) -> []:
        """
        :return: all assertions to be checked.
        """
        return self.specification.get_assertions()

    def __sanity_checks(self, strategy, tool_config):
        if strategy.name == 'BV':
            self.__separate_assertions = False
        if strategy.name not in self.config.strategy['supported']:
            raise AttributeError("Strategy {0} is not supported by tool configuration {1}".format(strategy.name,
                                                                                                  tool_config))

    def assemble_task_files(self, target_assertions, target_model=None, united_assertion=None):
        """
        Chooses files for checking assertions and model.
        :param target_assertions: assertions to be checked.
        :param target_model: specify type of model for assertions.
        :param united_assertion: use one specified assertion name for all assertions.
        """
        self.__task_files.clear()
        self.__task_files.extend(self.__sources)

        model = self.specification.update_model(target_model)
        self.config.configure_properties(target_assertions, united_assertion)

        if model == C_FILE:
            self.config.create_property_files()
            # TODO: fix this (RSG).
            if 'linux:alloc:spin lock' in target_assertions and \
                    'linux:spinlock' not in target_assertions:
                target_assertions.append('linux:spinlock')
            if ('linux:alloc:spin lock::wrong flags' in target_assertions or 'linux:alloc:spin lock::nonatomic'
                    in target_assertions) and 'linux:spinlock::one thread:double unlock' not in target_assertions:
                target_assertions.append('linux:spinlock::one thread:double unlock')

            self.__task_files.extend(self.specification.get_source_files(target_assertions))
            self.__task_files.append(self.specification.generate_assertions_map(target_assertions, united_assertion,
                                                                                self.config.strategy.get('explicit error function')))
        elif model == AUTOMATON:
            for file in glob.glob('*.spc'):
                os.remove(file)
            self.specification.copy_models(target_assertions, united_assertion)
        else:
            raise NotImplementedError('Model {0} for property formalization is not supported'.format(model))

    def execute_cil(self):
        """
        Takes all task files, executes CIL (if needed) and put result as a new task file.
        """
        cil_result_file = CIL_FILE
        tmp_files = ()
        for file in self.__task_files:
            trimmed_c_file = '_{0}.trimmed.i'.format(os.path.splitext(os.path.basename(file))[0])
            with open(file, encoding='ascii') as old_file, open(trimmed_c_file, 'w', encoding='ascii') as new_file:
                # Specify original location to avoid references to *.trimmed.i files in error traces.
                new_file.write('# 1 "{0}"\n'.format(file))
                # Each such expression occupies individual line, so just get rid of them.
                for line in old_file:
                    # TODO: other verifiers used to fail here.
                    if 'ignore builtins' in self.config.strategy and self.config.strategy.get('ignore builtins'):
                        if '__builtin_unreachable' in line:
                            continue
                        if re.search(r'long(.+)__builtin_expect', line):
                            line = re.sub("__builtin_expect", "__builtin_expect__", line)
                        if 'void __builtin_trap(void)' in line:
                            line = re.sub("__builtin_trap", "__builtin_trap__", line)
                    if 'explicit entry point' in self.config.strategy:
                        line = re.sub(self.config.entry_points[0], self.config.strategy.get('explicit entry point'), line)
                    new_file.write(re.sub(r'asm volatile goto.*;', '', line))

            tmp_files += (trimmed_c_file, )
        if self.config.merge_source_files:
            # TODO: put all those options somewhere.
            core.utils.execute(self.logger,
                       (
                           'cilly.asm.exe',
                           '--printCilAsIs',
                           '--domakeCFG',
                           '--decil',
                           '--noInsertImplicitCasts',
                           # Now supported by CPAchecker frontend.
                           '--useLogicalOperators',
                           '--ignore-merge-conflicts',
                           # Don't transform simple function calls to calls-by-pointers.
                           '--no-convert-direct-calls',
                           # Don't transform s->f to pointer arithmetic.
                           '--no-convert-field-offsets',
                           # Don't transform structure fields into variables or arrays.
                           '--no-split-structs',
                           '--rmUnusedInlines',
                           '--out', cil_result_file,
                       ) + tmp_files)
            self.__task_files = [cil_result_file]
            for file in tmp_files:
                os.remove(file)
        else:
            self.__task_files = list(tmp_files)

    def generate_benchmark_file(self, file_name):
        """
        Create benchmark.xml file based on specified configuration.
        :param file_name:
        """
        benchmark = self.config.generate_benchmark()
        tasks = ElementTree.SubElement(benchmark, "tasks")
        first = True
        for file in self.__task_files:
            if first:
                ElementTree.SubElement(tasks, "include").text = file
                first = False
            else:
                ElementTree.SubElement(tasks, "append").text = file
        with open(file_name, "w", encoding="ascii") as fp:
            fp.write(minidom.parseString(ElementTree.tostring(benchmark)).toprettyxml(indent="    "))

    def move_task_files(self, dst):
        """
        Move task files in specified directory.
        :param dst:
        """
        for file, content in self.config.propertyfiles.items():
            shutil.copy(file, dst)
        for file in self.__task_files:
            shutil.move(file, dst)
        for file in glob.glob("{0}*".format(re.sub(r'/', '-', self.name))):
            shutil.copy(file, dst)
        # Information for scheduler.
        scheduler_info = dict()
        scheduler_info['tool'] = self.config.tool
        scheduler_info['path'] = self.config.path
        with open("{0}/scheduler_config.json".format(dst), "w", encoding="ascii") as fp:
            json.dump(scheduler_info, fp, indent=4)


class SubmittedTask(object):
    """
    Represents verification task after its submission.
    In general case several submitted tasks can be bound to one verification task.
    """
    counter = 0

    def __init__(self, archive: str, session, resultfiles):
        self.archive = archive
        self.status = PENDING
        self.internal_identifier = str(self.counter)
        self.external_identifier = None
        self.session = session
        self.resultfiles = resultfiles

    def schedule_task(self, backwards):
        """
        Send submitted task to the scheduler.
        :param backwards:
        """
        # TODO: remove (backwards)
        backwards['files'] = [CIL_FILE]
        self.external_identifier = self.session.schedule_task(backwards)

    def get_status(self):
        """
        Get submitted task status.
        :return: submitted task status.
        """
        self.status = self.session.get_task_status(self.external_identifier)
        return self.status

    def __get_verifier_log_file(self):
        logs = set()
        for file in glob.glob(os.path.join('output', 'benchmark*logfiles/*')):
            logs.add(os.path.join(self.internal_identifier, file))
        return logs

    def __get_result_xml_file(self):
        xml_files = glob.glob(os.path.join('output', 'benchmark*results.xml'))
        return xml_files

    def __get_violated_assertion(self, file):
        for line in reversed(list(open(file))):
            result = re.search(r"<data key=\"violatedProperty\">(.*)</data>", line)
            if result:
                # Remove property extensions from its name.
                return result.group(1).replace('.spc', '').replace('.prp', '')
        return None

    def __get_error_traces(self):
        error_traces = {}
        for file in glob.glob(self.resultfiles):
            path = os.path.join(self.internal_identifier, file)
            assertion = self.__get_violated_assertion(file)
            if assertion not in error_traces:
                error_traces[assertion] = [path]
            else:
                error_traces[assertion].append(path)
        return error_traces

    def get_results(self):
        """
        Get result of solving verification tasks and create VerificationResults object based on it.
        :return: VerificationResults object.
        """
        self.session.download_decision(self.external_identifier)
        with tarfile.open("decision result files.tar.gz") as tar:
            tar.extractall()

        assertions = []
        global_verdict = UNKNOWN
        verdicts = {}
        resources = Resources()
        for file in self.__get_result_xml_file():
            with open(file, encoding='ascii') as f_res:
                dom = minidom.parse(f_res)
                for run in dom.getElementsByTagName('run'):
                    assertions = run.getAttribute('properties').split(PROPERTIES_SEPARATOR)  # TODO: sync with benchExec
                    for column in run.getElementsByTagName('column'):
                        title = column.getAttribute('title')
                        if title == 'status':
                            global_verdict = column.getAttribute('value')
                        match = re.search(r'status \((.+)\)', title)
                        if match:
                            found_assertion = match.groups()[0]
                            if found_assertion in assertions:
                                verdicts[found_assertion] = column.getAttribute('value')
                        if title == 'cputime':
                            resources.cpu_time = int(float(column.getAttribute('value')[:-1]) * 1000)
                        if title == 'walltime':
                            resources.wall_time = int(float(column.getAttribute('value')[:-1]) * 1000)
                        if title == 'memUsage':
                            resources.memory_usage = int(column.getAttribute('value'))

        if len(assertions) == 1:
            verdicts[assertions[0]] = global_verdict
        for assertion, verdict in verdicts.items():
            if 'true' in verdict:
                verdicts[assertion] = SAFE
            elif 'false' in verdict:
                verdicts[assertion] = UNSAFE
            else:
                # Save reason of global unknown in case of checking several properties.
                if global_verdict not in (SAFE, UNSAFE, UNKNOWN) \
                        and 'true' not in global_verdict and 'false' not in global_verdict:
                    verdicts[assertion] = global_verdict
        error_traces = self.__get_error_traces()
        if len(error_traces) == 1 and len(assertions) == 1:
            # Do not expect good property names here.
            error_traces[assertions[0]] = error_traces.popitem()[1]
        incompletes = []
        # TODO: does not work with CV+MEA (may require BenchExec or verifiers changes).
        for assertion, traces in error_traces.items():
            if not verdicts[assertion] == UNSAFE:
                # leave verdict unchanged for reason of unknown.
                incompletes.append(assertion)

        new_result = VerificationResults(resources=resources,
                                         verdicts=verdicts,
                                         logs=self.__get_verifier_log_file(),
                                         error_traces=error_traces,
                                         incompletes=incompletes)

        return new_result

    def get_error(self):
        task_error = self.session.get_task_error(self.external_identifier)
        return task_error


class VerificationConfig(object):
    """
    Representation of verification task configuration, which is based on tool config and task config.
    """

    def __init__(self, config_file, conf, specification: Specification, resources: Resources, name: str):
        self.tool = ""
        self.options = {}
        self.__raw_options = {}
        self.__configured_options = {}
        self.propertyfiles = {}
        self.propertyfiles_pattern = {}
        self.resultfiles = ""
        self.version = ""
        self.path = ""
        self.strategy = {}
        self.aux = {}
        self.merge_source_files = False
        try:
            with open(config_file, encoding='ascii') as f_config:
                config = json.load(f_config)
                for attr, val in config.items():
                    if attr == "tool":
                        self.tool = val
                    elif attr == "resultfiles":
                        self.resultfiles = val
                    elif attr == "propertyfiles":
                        self.propertyfiles_pattern = val
                    elif attr == "options":
                        self.options = val
                    elif attr == "raw options":
                        self.__raw_options = val
                    elif attr == "version":
                        self.version = val
                    elif attr == "strategy":
                        self.strategy = val
                    elif attr == "path":
                        self.path = val
                    else:
                        self.aux[attr] = val
                assert self.tool and self.resultfiles
        except IOError:
            raise RuntimeError('Error during reading of configuration file {0}'.format(config_file))

        self.limits = resources

        if 'options' in conf['VTG strategy']['verifier']:
            self.options.extend(conf['VTG strategy']['verifier']['options'])

        if 'merge source files' in conf['VTG strategy']:
            self.merge_source_files = conf['VTG strategy']['merge source files']

        # entry points
        self.entry_points = conf['abstract task desc']['entry points']
        if len(self.entry_points) > 1:
            raise NotImplementedError('Several entry points are not supported')

        if 'separate assertion' in self.strategy:
            specification.update_separate_assertions(self.strategy['separate assertion'])
        self.__organize_options(specification, name)

        # defaults
        if 'external filtering' not in self.strategy:
            self.strategy['external filtering'] = 'no'

    def __organize_options(self, specification: Specification, name: str):
        # This is very important function
        organized = []
        cache = []

        # TODO: expand this
        key_val_list = [('${memory_limit}', str(self.limits.memory_usage)),
                        ('${time_limit}', str(self.limits.cpu_time)),
                        ('${entry_point}', str(self.entry_points[0])),
                        ('${number_of_assertions}', str(len(specification.get_assertions()))),
                        ('${sourcefile_name}', str(re.sub(r'/', '-', name)))
                        ]

        for option in self.options:
            for key, value in option.items():
                for (defined, val) in key_val_list:
                    value = value.replace(defined, val)
                match = re.search(r'\{\{i\s*(.+)\s*i\}\}', value)
                if match:
                    value = re.sub(re.escape(match.group(0)), str(int(eval(match.groups()[0]))), value)
                if '{0}{1}'.format(key, value) not in cache:
                    cache.append('{0}{1}'.format(key, value))
                    organized.append({key: value})
        self.options = organized

    def configure_properties(self, assertions, unite_assertion=None):
        # This is very important function
        organized = {}
        for assertion in assertions:
            key_val_list = [('${assertion}', str(unite_assertion or assertion)),
                            ('${entry_point}', str(self.entry_points[0])),
                            ('${assertion_escape}', str(re.sub(r'\W', '_', unite_assertion or assertion)))
                            ]

            for name, value in self.propertyfiles_pattern.items():
                for (defined, val) in key_val_list:
                    name = name.replace(defined, val)
                    value = value.replace(defined, val)
                organized[name] = value
            if unite_assertion:
                break
        self.propertyfiles = organized

    def create_property_files(self):
        """
        Create property files based on specified configuration.
        """
        for name, content in self.propertyfiles.items():
            with open(name, 'w', encoding='ascii') as propertyfile:
                propertyfile.write(content)

    def generate_benchmark(self):
        """
        Generate xml benchmark content for configuration.
        :return:
        """
        benchmark = ElementTree.Element("benchmark", {
            "tool": self.tool.lower(),
            "timelimit": str(round(self.limits.cpu_time / 1000)),
            "memlimit": str(self.limits.memory_usage) + "B",
        })
        rundefinition = ElementTree.SubElement(benchmark, "rundefinition")
        for opt in self.options:
            for name in opt:
                ElementTree.SubElement(rundefinition, "option", {"name": name}).text = opt[name]
        for opt in self.__configured_options:
            for name in opt:
                ElementTree.SubElement(rundefinition, "option", {"name": name}).text = opt[name]
        # Property file may not be specified.
        for propertyfile, content in self.propertyfiles.items():
            ElementTree.SubElement(benchmark, "propertyfile").text = propertyfile
        return benchmark


class VerificationResults(object):
    """
    Result of solving a VerificationTask.
    """

    def __init__(self, verdicts={}, error_traces={}, reasons={}, resources=None, logs=set(), incompletes=[]):
        self.verdicts = verdicts  # map assert->verdict
        self.error_traces = error_traces  # map assert->list of traces
        self.reasons = reasons  # map assert->reason of unknown
        if resources:
            self.resources = resources
        else:
            self.resources = Resources()
        self.logs = logs
        self.incomplete_unsafes = incompletes

    def update(self, verification_result):
        """
        Update results based on another tool launch.
        :param verification_result:
        """
        self.verdicts.update(verification_result.verdicts)
        self.error_traces.update(verification_result.error_traces)
        self.reasons.update(verification_result.reasons)  # TODO: those are unused
        self.resources.update(verification_result.resources)
        self.logs.update(verification_result.logs)
        self.incomplete_unsafes.extend(verification_result.incomplete_unsafes)

    def get_checked_assertions(self):
        """
        Get set of assertions, which still has not got verdicts.
        :return:
        """
        result = set()
        for assertion, verdict in self.verdicts.items():
            if verdict not in (SAFE, UNSAFE):
                result.add(assertion)
        return result

    def is_empty(self):
        """
        Check if task was partially solved.
        :return:
        """
        return not bool(self.verdicts)

    def is_solved(self):
        """
        Check if task was fully successfully solved.
        :return:
        """
        for assertion, verdict in self.verdicts.items():
            if verdict not in (SAFE, UNSAFE):
                return False
        return True
