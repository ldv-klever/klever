#!/usr/bin/python3

import time
import os
import shutil
import glob
import tarfile

import core.utils
import core.session

from core.vtg.libraries.mea import MEA
from core.vtg.strategies import Strategy
from core.vtg.data_structures import VerificationTask, VerificationResults, Specification, Resources, SubmittedTask, \
    C_FILE, AUTOMATON, SAFE, UNSAFE, UNKNOWN
from core.vtg.libraries.et import process_et

POLL_INTERVAL_DEFAULT = 10
POLL_INTERVAL_TAG = "poll interval"
ERROR = "ERROR"
FINISHED = "FINISHED"
TOOL_CONFIG_NAME = "tools_configurations"
TOOL_CONFIG_TAG = "tool config"
BENCHMARK_FILE_NAME = "benchmark.xml"
SUBMITTED_ARCHIVE = "task files.tar.gz"
GLOBAL_ERROR_FILE = "task error.txt"
UNKNOWN_FILE = "error.txt"


def create_task(strategy: Strategy, predefined_config=None, limitations_factor=None,
                specified_assertions=set()) -> (VerificationTask, []):
    """
    Extracts information regarding verification task from strategy component and
    creates VerificationTask object based on it.
    :param strategy: strategy to solve verification task (component object).
    :param predefined_config: use specified tool configuration rather than taken from config.
    :param limitations_factor: 0.0 < factor <= 1.0, which is used to allocate factor times resources
    :param specified_assertions: use specified assertions rather than taken from config.
    :return: created VerificationTask object.
    """
    name = ""
    for attr in strategy.conf['abstract task desc']['attrs']:
        attr_name = list(attr.keys())[0]
        attr_val = attr[attr_name]
        if attr_name == 'verification object':
            name = attr_val
    sources = []
    specification = Specification()

    for received_sources in strategy.conf['abstract task desc']['extra C files']:
        if 'bug kinds' not in received_sources:
            # Source file without specification
            sources.append(os.path.join(strategy.conf['main working directory'], received_sources[C_FILE]))
        else:
            # Specification files
            specification_files = {}
            if C_FILE in received_sources:
                specification_files[C_FILE] = os.path.join(strategy.conf['main working directory'],
                                                           received_sources[C_FILE])
            if AUTOMATON in received_sources:
                specification_files[AUTOMATON] = os.path.join(strategy.conf['main working directory'],
                                                              received_sources[AUTOMATON])
            if specification_files:
                specification.add_model(specification_files, received_sources['bug kinds'])

    overall_assertions = specification.get_assertions()
    if specified_assertions:

        basic_assertions_number = len(overall_assertions)
        for assertion in specification.get_assertions():
            if assertion not in specified_assertions:
                specification.delete_model(assertion)
        limitations_factor = len(specification.get_assertions()) / basic_assertions_number

    tools_config_path = TOOL_CONFIG_NAME
    tools_config = predefined_config or strategy.conf["VTG strategy"]["verifier"][TOOL_CONFIG_TAG]
    config_file = os.path.join(core.utils.find_file_or_dir(strategy.logger,
                                                           strategy.conf['main working directory'],
                                                           tools_config_path), tools_config)
    # Limitations
    limits = Resources(cpu_time=strategy.conf['VTG strategy']['resource limits']['CPU time'],
                       memory_usage=strategy.conf['VTG strategy']['resource limits']['memory size'])
    if limitations_factor:
        limits.cpu_time = int(limits.cpu_time * limitations_factor)
    verification_task = VerificationTask(name, sources, specification, config_file, strategy, limits)
    return verification_task, overall_assertions


def update_task(strategy: Strategy, verification_task: VerificationTask, verification_result: VerificationResults,
                config: str, limitations_factor):
    """
    Update created with create_task VerificationTask by removing assertions,
    which already have received verdicts, and adjusting resource limitations.
    :param strategy:
    :param verification_task:
    :param verification_result:
    :param config:
    :param limitations_factor:
    :return:
    """
    limits = Resources(cpu_time=strategy.conf['VTG strategy']['resource limits']['CPU time'],
                       memory_usage=strategy.conf['VTG strategy']['resource limits']['memory size'])
    limits.cpu_time = int((limits.cpu_time - verification_result.resources.cpu_time) * limitations_factor)

    for assertion, verdict in verification_result.verdicts.items():
        if verdict in (SAFE, UNSAFE):
            verification_task.specification.delete_model(assertion)

    tools_config_path = TOOL_CONFIG_NAME
    config_file = os.path.join(core.utils.find_file_or_dir(strategy.logger,
                                                           strategy.conf['main working directory'],
                                                           tools_config_path), config)
    verification_task.update_config(config_file, strategy, limits)
    return verification_task


def submit_task(task: VerificationTask, strategy: Strategy) -> SubmittedTask:
    """
    Creates archive for VerificationTask object (which contains property files, task files and benchmark.xml)
    and sends it to the scheduler.
    :param task: VerificationTask object.
    :param strategy: component object.
    :return: SubmittedTask objects with unique identifier.
    """
    benchmark_file = BENCHMARK_FILE_NAME
    task.generate_benchmark_file(benchmark_file)
    SubmittedTask.counter += 1
    new_dir = str(SubmittedTask.counter)
    os.makedirs(new_dir)
    shutil.move(benchmark_file, new_dir)
    task.move_task_files(new_dir)
    os.chdir(new_dir)

    archive_name = SUBMITTED_ARCHIVE
    with tarfile.open(archive_name, 'w:gz') as tar:
        for file in glob.glob("*"):
            tar.add(file)

    session = core.session.Session(strategy.logger, strategy.conf['Klever Bridge'], strategy.conf['identifier'])
    submitted_task = SubmittedTask(os.path.abspath(archive_name), session, task.config.resultfiles)

    # TODO: should be removed (backwards)
    must_be_reimplemented = {
        'id': strategy.conf['abstract task desc']['id'],
        'format': 1,
    }
    for attr_name in ('priority', 'upload input files of static verifiers'):
        must_be_reimplemented[attr_name] = strategy.conf[attr_name]
    must_be_reimplemented.update(
        {name: strategy.conf['VTG strategy'][name] for name in ('resource limits', 'verifier')})

    submitted_task.schedule_task(must_be_reimplemented)
    strategy.logger.info("Task {0} ({1}) has been submitted".format(submitted_task.external_identifier,
                                                                    submitted_task.internal_identifier))

    os.chdir("..")

    return submitted_task


def wait_for_submitted_tasks(submitted_tasks: list(), strategy: Strategy) -> VerificationResults:
    """
    Waits for all submitted tasks and creates joint results.
    :param submitted_tasks: List of SubmittedTask objects.
    :param strategy: component object.
    :return: results of solving tasks.
    """
    verification_result = VerificationResults()
    if POLL_INTERVAL_TAG in strategy.conf['VTG strategy'] and strategy.conf['VTG strategy'][POLL_INTERVAL_TAG]:
        poll_interval = strategy.conf['VTG strategy'][POLL_INTERVAL_TAG]
    else:
        poll_interval = POLL_INTERVAL_DEFAULT
    while submitted_tasks:
        for task in submitted_tasks:
            status = task.get_status()
            strategy.logger.debug("Submitted task {0} ({1}), status: {2}".format(task.external_identifier,
                                                                                 task.internal_identifier,
                                                                                 status))

            if status == FINISHED:
                os.chdir(task.internal_identifier)
                verification_result.update(task.get_results())
                os.chdir('..')
            if status == ERROR:
                task_error = task.get_error()
                strategy.logger.warning('Failed to decide verification task {0}: {1}'.format(task.external_identifier,
                                                                                             task_error))
                __process_global_error(strategy, task_error, task.internal_identifier)

        submitted_tasks = [task for task in submitted_tasks if (task.status != FINISHED and task.status != ERROR)]
        if not submitted_tasks:
            break
        time.sleep(poll_interval)
    strategy.logger.info("All submitted tasks have been completed")
    return verification_result


def __process_global_error(strategy: Strategy, task_error: str, identifier: str):
    strategy.logger.warning('Failed to decide verification task: {0}'.format(task_error))
    with open(GLOBAL_ERROR_FILE, 'w', encoding='ascii') as fp:
        fp.write(task_error)
    core.utils.report(strategy.logger,
                      UNKNOWN,
                      {
                          'id': strategy.id + '/unknown/{0}'.format(identifier),
                          'parent id': strategy.id,
                          'problem desc': GLOBAL_ERROR_FILE,
                          'files': [GLOBAL_ERROR_FILE]
                      },
                      strategy.mqs['report files'],
                      strategy.conf['main working directory'],
                      identifier)


def process_result(results: VerificationResults, strategy: Strategy, task: VerificationTask):
    """
    Creates reports based on the given VerificationResults object.
    :param results: Results of solving verification task.
    :param strategy: component object.
    :param task:
    """
    # TODO: remove task argument.
    # TODO: add several logs here?
    if not strategy.logger.disabled:
        tool_common_log = "tool.log"
        with open(tool_common_log, 'w') as outfile:
            for file in results.logs:
                with open(file) as infile:
                    outfile.write(infile.read())
    else:
        tool_common_log = None
    verification_report_id = '{0}/verification'.format(strategy.id)
    core.utils.report(strategy.logger,
                      'verification',
                      {
                          'id': verification_report_id,
                          'parent id': strategy.id,
                          'attrs': [],
                          'name': task.config.tool,
                          'resources': results.resources.get_basic_representation(),
                          'log': tool_common_log,
                          'files': [tool_common_log] if tool_common_log else []
                      },
                      strategy.mqs['report files'],
                      strategy.conf['main working directory'])
    if tool_common_log:
        os.remove(tool_common_log)

    for assertion in results.incomplete_unsafes:
        strategy.logger.info('Assertion {0} got unsafe-incomplete verdict'.format(assertion))
        name = 'unsafe-incomplete{0}.txt'.format(assertion)
        with open(name, 'w', encoding='ascii') as fp:
            fp.write('Unsafe-incomplete due to {0}'.format(results.verdicts[assertion]))
        core.utils.report(strategy.logger,
                          UNKNOWN,
                          {
                              'id': verification_report_id + '/unsafe-incomplete/{0}'.format(assertion),
                              'parent id': verification_report_id,
                              'attrs': [{"Rule specification": assertion}],
                              'problem desc': name,
                              'files': [name]
                          },
                          strategy.mqs['report files'],
                          strategy.conf['main working directory'],
                          assertion + "ui")

    for assertion, verdict in results.verdicts.items():
        if assertion in results.error_traces and results.error_traces[assertion]:

            start_time = time.time()
            start_time_cpu = time.process_time()

            if len(results.error_traces[assertion]) == 1:
                filtered_error_traces = results.error_traces[assertion]
            else:
                mea = MEA(strategy.conf, strategy.logger, results.error_traces[assertion], assertion,
                          task.config.strategy['external filtering'])
                filtered_error_traces = mea.execute()

                # Adding statistics on spent resources.
                spent_time = int((time.time() - start_time) * 1000)
                spent_time_cpu = int((time.process_time() - start_time_cpu) * 1000)
                resources = Resources(cpu_time=spent_time_cpu, wall_time=spent_time)
                core.utils.report(strategy.logger,
                                  'verification',
                                  {
                                      'id': "{0}/{1}/mea".format(strategy.id, assertion),
                                      'parent id': strategy.id,
                                      'name': "MEA",
                                      'attrs': [],
                                      'resources': resources.get_basic_representation(),
                                      'log': None
                                  },
                                  strategy.mqs['report files'],
                                  strategy.conf['main working directory'],
                                  "{0}.mea".format(assertion))

                strategy.logger.info('{0} error traces for assertion {1} were filtered into {2}'.format(
                    len(results.error_traces[assertion]), assertion, len(filtered_error_traces)
                ))

            for error_trace in filtered_error_traces:
                __process_single_verdict(strategy, UNSAFE, verification_report_id, assertion,
                                         specified_error_trace=error_trace)

        else:
            __process_single_verdict(strategy, verdict, verification_report_id, assertion)

    core.utils.report(strategy.logger,
                      'verification finish',
                      {'id': verification_report_id},
                      strategy.mqs['report files'],
                      strategy.conf['main working directory'])

    if strategy.logger.disabled:
        __free_resources()


def __free_resources():
    # Clear work directory in production mode.
    for file in os.listdir(os.getcwd()):
        shutil.rmtree(file, ignore_errors=True)


def __process_single_verdict(strategy, verdict, verification_report_id, assertion, specified_error_trace=None):

    strategy.process_single_verdict(assertion, verdict)

    added_attrs = list()
    added_attrs.append({"Rule specification": assertion})

    strategy.logger.info('Verification task decision status is "{0}"'.format(verdict))

    if verdict == SAFE:
        core.utils.report(strategy.logger,
                          SAFE,
                          {
                              'id': verification_report_id + '/safe/{0}'.format(assertion or ''),
                              'parent id': verification_report_id,
                              'attrs': added_attrs,
                              'proof': None
                          },
                          strategy.mqs['report files'],
                          strategy.conf['main working directory'],
                          assertion)
    elif verdict == UNSAFE:
        assert specified_error_trace
        assertion = "{0}.{1}".format(assertion, os.path.basename(specified_error_trace))
        verification_report_id_unsafe = "{0}/unsafe/{1}".format(verification_report_id, assertion)
        path_to_processed_witness = specified_error_trace + ".processed"
        strategy.logger.debug('Create processed error trace file "{0}"'.format(path_to_processed_witness))

        # If we cannot process only one error trace, we should not kill the whole strategy and lose all results.
        try:
            (graphml, src_files) = process_et(strategy.logger, specified_error_trace)
            with open(path_to_processed_witness, 'w', encoding='utf8') as fp:
                graphml.writexml(fp)
        except:
            strategy.logger.warning("Error trace was not processed normally")
            shutil.copy(specified_error_trace, path_to_processed_witness)
            src_files = []

        core.utils.report(strategy.logger,
                          UNSAFE,
                          {
                              'id': verification_report_id_unsafe,
                              'parent id': verification_report_id,
                              'attrs': added_attrs,
                              'error trace': path_to_processed_witness,
                              'files': [path_to_processed_witness] + list(src_files)
                          },
                          strategy.mqs['report files'],
                          strategy.conf['main working directory'],
                          assertion)
    else:
        with open(UNKNOWN_FILE, 'w', encoding='ascii') as fp:
            fp.write(verdict)
        core.utils.report(strategy.logger,
                          UNKNOWN,
                          {
                              'id': verification_report_id + '/unknown/{0}'.format(assertion or ''),
                              'parent id': verification_report_id,
                              'attrs': added_attrs,
                              'problem desc': UNKNOWN_FILE,
                              'files': [UNKNOWN_FILE]
                          },
                          strategy.mqs['report files'],
                          strategy.conf['main working directory'],
                          assertion)
