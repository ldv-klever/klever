import argparse
import getpass
import json
import multiprocessing
import os
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

_default_conf_file = 'psi-conf.json'
_conf = None
_logger = None
_job_class_components = {'Verification of Linux kernel modules': [psi.lkbce.lkbce, psi.lkvog.lkvog],
                         # These components are likely appropriate for all job classes.
                         'Common': [psi.avtg.avtg, psi.vtg.vtg]}


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

        start_report_file = psi.utils.dump_report(_logger, 'start',
                                                  {'id': '/', 'attrs': [{'psi version': version}], 'comp': comp})

        session = psi.session.Session(_logger, omega['user'], omega['passwd'], _conf['Omega']['name'])
        session.decide_job(job, start_report_file)

        # TODO: create parallel process to send requests about successful operation to Omega.

        reports_mq = multiprocessing.Queue()
        reports_p = multiprocessing.Process(target=_send_reports, args=(session, reports_mq))
        reports_p.start()

        job.extract_archive()

        components_conf = _create_components_conf(comp)

        job.get_class()

        # Use Psi logger to report events that are common to all components.
        components = _get_components(job.type)
        # Component callbacks aren't obtained in parallel since it is quite fast.
        for component in components:
            p = component.PsiComponentCallbacks(component, components_conf, _logger)
            p.start()
            p.join()

        component_processes = []
        for component in components:
            # Use the same reports MQ in all components.
            # TODO: fix passing of MQs after all.
            p = component.PsiComponent(component, components_conf, _logger, reports_mq)
            p.start()
            component_processes.append(p)

        _logger.info('Wait for components')
        # Every second check whether some component died. Otherwise even if some non-first component will die we
        # will wait for all components that preceed that failed component prior to notice that something went wrong.
        while True:
            # The number of components that are still operating.
            operating_components_num = 0

            for p in component_processes:
                p.join(1.0 / len(component_processes))
                operating_components_num += p.is_alive()

            if not operating_components_num:
                break

        raise Exception('TODO: remove me after all!')
    except Exception as e:
        _exit_code = 1

        if 'reports_mq' in locals():
            with open('problem desc', 'w') as fp:
                traceback.print_exc(file=fp)

            with open('problem desc') as fp:
                unknown_report_file = psi.utils.dump_report(_logger, 'unknown',
                                                            {'id': 'unknown', 'parent id': '/',
                                                             'problem desc': fp.read()})
                reports_mq.put(unknown_report_file)

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

        if 'reports_mq' in locals():
            with open(conf_file) as conf_fp:
                with open('log') as log_fp:
                    finish_report_file = psi.utils.dump_report(_logger, 'finish',
                                                               {'id': '/',
                                                                'resources': psi.utils.count_consumed_resources(
                                                                    _logger, start_time),
                                                                'desc': conf_fp.read(),
                                                                'log': log_fp.read(),
                                                                'data': ''})
                    reports_mq.put(finish_report_file)

            _logger.info('Send terminator to reports message queue')
            reports_mq.put('__terminator__')

            _logger.info('Wait for uploading all reports')
            reports_p.join()
            exit_code = exit_code if 'exit_code' in locals() else reports_p.exitcode

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

    components_conf.update(
        {'root id': os.path.abspath(os.path.curdir), 'sys': {'CPUs num': cpus_num, 'mem size': mem_size},
         'job priority': _conf['job']['priority'],
         'abstract verification tasks gen priority': _conf['abstract verification tasks gen priority'],
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


def _send_reports(session, reports_mq):
    try:
        while True:
            m = reports_mq.get()
            if m == '__terminator__':
                _logger.debug('Report messages queue was terminated')
                break
            _logger.debug('Upload report "{0}"'.format(m))
            session.upload_report(m)
    except Exception as e:
        # If we can't send reports to Omega by some reason we can just silently die.
        _logger.exception('Catch exception when sending reports to Omega')
        exit(1)
