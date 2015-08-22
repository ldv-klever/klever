import argparse
import getpass
import io
import json
import multiprocessing
import os
import re
import shutil
import time
import traceback

import psi.job
import psi.session
import psi.utils

# Psi components.
import psi.lkbce.lkbce
import psi.lkvog.lkvog
import psi.avtg.avtg
import psi.vtg.vtg
import psi.vtsc.vtsc

_default_conf_file = 'psi-conf.json'
_conf = None
_logger = None
_job_class_components = {'Verification of Linux kernel modules': [psi.lkbce.lkbce, psi.lkvog.lkvog],
                         # These components are likely appropriate for all job classes.
                         'Common': [psi.avtg.avtg, psi.vtg.vtg, psi.vtsc.vtsc]}


def launch():
    """
    Main Psi function.
    """
    try:
        global _conf, _logger

        # Remember approximate time of start to count wall time.
        start_time = time.time()

        conf_file = _get_conf_file()

        # Read configuration from file.
        with open(conf_file) as fp:
            _conf = json.load(fp)

        is_solving_file, is_solving_file_fp = _prepare_work_dir()

        # Remember path to configuration file relative to working directory before changing directory.
        conf_file = os.path.relpath(conf_file, _conf['work dir'])

        # Move to working directory until the end of operation.
        # We can use path for "is solving" file relative to working directory since exceptions aren't raised when we
        # have relative path but don't change directory yet.
        is_solving_file = os.path.relpath(is_solving_file, _conf['work dir'])
        os.chdir(_conf['work dir'])

        _logger = psi.utils.get_logger(os.path.basename(__file__), _conf['logging'])

        # Configuration for Omega.
        omega = {'user': _get_user('Omega'), 'passwd': _get_passwd('Omega')}

        version = _get_version()

        job = psi.job.Job(_logger, _conf['job']['id'])

        comp = psi.utils.get_comp_desc(_logger)

        start_report_file = psi.utils.report(_logger,
                                             'start',
                                             {'id': '/',
                                              'attrs': [{'psi version': version}],
                                              'comp': comp})

        session = psi.session.Session(_logger, omega['user'], omega['passwd'], _conf['Omega']['name'])
        session.decide_job(job, start_report_file)

        # TODO: create parallel process to send requests about successful operation to Omega.

        report_files_mq = multiprocessing.Queue()
        reporting_p = multiprocessing.Process(target=_send_reports, args=(session, report_files_mq))
        reporting_p.start()

        job.extract_archive()

        job.get_class()

        components = _get_components(job.type)

        # Do not read anything from job directory untill job class will be examined (it might be unsupported). This
        # differs from specification that doesn't treat unsupported job classes at all.
        components_conf = _create_components_conf(comp)

        # Use the same configuration and report files MQ in all components.
        context = {'components': components,
                   'components conf': components_conf,
                   'MQs': {'report files': report_files_mq}}
        psi.utils.invoke_callbacks(_logger, _launch_all_components, components, context)
        component_processes = context['component processes']

        _logger.info('Wait for components')
        # Every second check whether some component died. Otherwise even if some non-first component will die we
        # will wait for all components that preceed that failed component prior to notice that something went wrong.
        while True:
            # The number of components that are still operating.
            operating_components_num = 0

            for p in component_processes:
                p.join(1.0 / len(component_processes))
                operating_components_num += p.is_alive()

            if not operating_components_num or reporting_p.exitcode:
                break

        raise Exception('TODO: remove me after all!')
    except Exception as e:
        _exit_code = 1

        if 'report_files_mq' in locals():
            with open('problem desc', 'w') as fp:
                traceback.print_exc(file=fp)

            with open('problem desc') as fp:
                psi.utils.report(_logger,
                                 'unknown',
                                 {'id': 'unknown',
                                  'parent id': '/',
                                  'problem desc': '__file:problem desc'},
                                 report_files_mq)

        if _logger:
            _logger.exception('Catch exception')
        else:
            traceback.print_exc()
    finally:
        if 'component_processes' in locals():
            for p in component_processes:
                # Do not terminate components that already exitted.
                if p.is_alive():
                    p.terminate()
                    p.join()

        if 'report_files_mq' in locals():
            psi.utils.report(_logger,
                             'finish',
                             {'id': '/',
                              'resources': psi.utils.count_consumed_resources(
                                  _logger,
                                  start_time),
                              'desc': '__file:{0}'.format(conf_file),
                              'log': '__file:log',
                              'data': ''},
                             report_files_mq)

            _logger.info('Terminate report files message queue')
            report_files_mq.put(None)

            _logger.info('Wait for uploading all reports')
            reporting_p.join()
            if 'exit_code' not in locals():
                exit_code = reporting_p.exitcode

        if 'session' in locals():
            session.sign_out()

        if 'is_solving_file_fp' in locals() and not is_solving_file_fp.closed:
            if _logger:
                _logger.info('Release working directory')
            os.remove(is_solving_file)

        if 'exit_code' in locals():
            exit(exit_code)


def _check_another_psi(is_solving_file):
    """
    Check whether another Psi occupies the working directory.
    :param is_solving_file: file that means that the working directory is occupied.
    :raise FileExistsError: another Psi occupies the working directory.
    """
    if os.path.isfile(is_solving_file):
        raise FileExistsError('Another Psi occupies working directory "{0}"'.format(_conf['work dir']))


def _create_components_conf(comp):
    """
    Create configuration to be used by all Psi components.
    :param comp: a computer description returned by psi.utils.get_comp_desc().
    """
    _logger.info('Create components configuration')

    components_conf = {}
    # Read job configuration from file.
    with open('job/root/conf.json') as fp:
        components_conf = json.load(fp)

    for comp_param in comp:
        if 'CPUs num' in comp_param:
            cpus_num = comp_param['CPUs num']
        elif 'mem size' in comp_param:
            mem_size = comp_param['mem size']
        elif 'arch' in comp_param:
            arch = comp_param['arch']

    components_conf.update(
        {'root id': os.path.abspath(os.path.curdir), 'sys': {'CPUs num': cpus_num, 'mem size': mem_size, 'arch': arch},
         'job priority': _conf['job']['priority'],
         'abstract verification tasks gen priority': _conf['abstract verification tasks gen priority'],
         'debug': _conf['debug'],
         'allow local source directories use': _conf['allow local source directories use'],
         'parallelism': _conf['parallelism'],
         'logging': _conf['logging']})

    _logger.debug('Create components configuration file "components conf.json"')
    with open('components conf.json', 'w') as fp:
        json.dump(components_conf, fp, sort_keys=True, indent=4)

    return components_conf


def _get_components(kind):
    _logger.info('Get components necessary to solve job')

    if kind not in _job_class_components:
        raise KeyError('Job class "{0}" is not supported'.format(kind))

    # Get modules of components specific for job class.
    components = _job_class_components[kind]

    # Get modules of common components.
    if 'Common' in _job_class_components:
        components.extend(_job_class_components['Common'])

    _logger.debug(
        'Components to be launched: "{0}"'.format(', '.join([component.__package__ for component in components])))

    return components


def _get_conf_file():
    """
    Try to get configuration file from command-line options. If it is not specified, then use the default one.
    :return: a configuration file.
    """
    parser = argparse.ArgumentParser(description='Main script of Psi.')
    parser.add_argument('conf file', nargs='?', default=_default_conf_file,
                        help='configuration file (default: {0})'.format(_default_conf_file))
    return vars(parser.parse_args())['conf file']


def _get_passwd(name):
    """
    Get password for the specified name either from configuration or by using password prompt.
    :param name: a name of service for which password is required.
    :return: a password for the specified name.
    """
    _logger.info('Get ' + name + ' password')
    passwd = getpass.getpass() if not _conf[name]['passwd'] else _conf[name]['passwd']
    return passwd


def _get_user(name):
    """
    Get user for the specified name either from configuration or by using OS user.
    :param name: a name of service for which user is required.
    :return: a user for the specified name.
    """
    _logger.info('Get ' + name + ' user name')
    user = getpass.getuser() if not _conf[name]['user'] else _conf[name]['user']
    _logger.debug(name + ' user name is "{}"'.format(user))
    return user


def _get_version():
    """
    Get version either as a tag in the Git repository of Psi or from the file created when installing Psi.
    :return: a version.
    """
    # Git repository directory may be located in parent directory of parent directory.
    git_repo_dir = os.path.join(os.path.dirname(__file__), '../../.git')
    if os.path.isdir(git_repo_dir):
        version = psi.utils.get_entity_val(_logger, 'version',
                                           'git --git-dir {0} describe --always --abbrev=7 --dirty'.format(
                                               git_repo_dir))
    else:
        # TODO: get version of installed Psi.
        version = ''

    return version


def _launch_all_components(context):
    component_processes = []

    for component in context['components']:
        p = component.PsiComponent(component, context['components conf'], _logger, context['components'],
                                   context['MQs'])
        p.start()
        component_processes.append(p)

    context['component processes'] = component_processes


def _prepare_work_dir():
    """
    Clean up and create the working directory. Prevent simultaneous usage of the same working directory.
    """
    # Test whether another Psi occupies the same working directory.
    is_solving_file = os.path.join(_conf['work dir'], 'is solving')
    _check_another_psi(is_solving_file)

    # Remove (if exists) and create (if doesn't exist) working directory.
    # Note, that shutil.rmtree() doesn't allow to ignore files as required by specification. So, we have to:
    # - remove the whole working directory (if exists),
    # - create working directory (pass if it is created by another Psi),
    # - test one more time whether another Psi occupies the same working directory,
    # - occupy working directory.
    shutil.rmtree(_conf['work dir'], True)

    os.makedirs(_conf['work dir'], exist_ok=True)

    _check_another_psi(is_solving_file)

    # Occupy working directory until the end of operation.
    # Yes there may be race condition, but it won't be.
    return is_solving_file, open(is_solving_file, 'w')


def _send_reports(session, report_files_mq):
    try:
        while True:
            report_file = report_files_mq.get()

            if report_file is None:
                _logger.debug('Report files message queue was terminated')
                break

            _logger.info('Upload report file "{0}"'.format(report_file))
            with open(report_file) as fp:
                report = json.load(fp)
            # Read content of files specified via "__file:".
            for key in report:
                if isinstance(report[key], str):
                    match = re.search(r'^__file:(.+)$', report[key])
                    if match:
                        # All these files should be placed in the same directory as uploaded report file.
                        file = os.path.join(os.path.dirname(report_file), match.groups()[0])
                        # As well these files may not exist.
                        with open(file) if os.path.isfile(file) else io.StringIO('') as fp:
                            report[key] = fp.read()
            session.upload_report(json.dumps(report))
    except Exception as e:
        # If we can't send reports to Omega by some reason we can just silently die.
        _logger.exception('Catch exception when sending reports to Omega')
        exit(1)
