#!/usr/bin/env python3 -u

import fcntl
import datetime
import json
import yaml
import logging
import os
import re
import subprocess
import sys
import time
import argparse

from klever.cli import Cli

def get_logger(name):
    logger = logging.getLogger(name)
    logger.setLevel(logging.INFO)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s (script:%(lineno)03d) %(levelname)s> %(message)s',
                                  "%Y-%m-%d %H:%M:%S")
    handler.setFormatter(formatter)
    logger.addHandler(handler)

    return logger


def _execute_cmd(logger, *args, stdin=None, cwd=None, get_output=False):
    logger.info('Execute command "{0}"'.format(' '.join(args)))

    kwargs = {
        'stdin': stdin,
        'cwd': cwd
    }

    if get_output:
        return subprocess.check_output(args, **kwargs).decode('utf8')
    else:
        subprocess.check_call(args, **kwargs)


def execute_cmd(logger, *args, stdin=None, cwd=None, get_output=False):
    try:
        return _execute_cmd(logger, *args, stdin=stdin, cwd=cwd, get_output=get_output)
    except subprocess.CalledProcessError:
        error(logger, 'Could not execute command')


def error(logger, msg):
    logger.error(msg)
    sys.exit(1)

def run_job(job, logger):
    logger.info('Start decision of job {0} ({1})'.format(job['name'], job['id']))
    run_data = 'ci-config/validation job decision configuration.json' if job.get('validation') else 'ci-config/job decision configuration.json'

    cli = Cli('localhost:8998', 'manager', 'manager')
    _, job_uuid = cli.create_job(job['id'])
    _, decision_uuid = cli.start_job_decision(job_uuid, rundata=run_data)

    # Wait till job will be decided somehow.
    while True:
        time.sleep(5)

        job_version_solution_progress = cli.decision_progress(decision_uuid)

        if int(job_version_solution_progress['status']) > 2:
            break

    results = cli.decision_results(decision_uuid)

    if not results:
        error(logger, 'No results found for {}'.format(job['name']))

    return results

def compare_results(job, regr_test_results, job_version_solution_results):
    def mark_in(mark_id, verdict_type, verdict):
        return verdict_type in regr_test_results and \
            mark_id in regr_test_results[verdict_type].get(verdict, [])

    error_msgs = []

    status = int(job_version_solution_results['status'])
    if status != 3:
        return 'Testing/validation job failed: ' + job

    for verdict in ('safes', 'unsafes', 'unknowns'):
        new_marks = []
        matched_marks = []
        job_verdict_result = job_version_solution_results[verdict]

        for i, report in enumerate(job_verdict_result['reports']):
            # Do not hurt if there are several associated unknown marks for unknowns since this is quite naturally.
            if len(report['marks']) != 1 and (verdict != 'unknowns' or len(report['marks']) < 1):
                error_msgs.append(
                    'There are {0} associations for report "{1}" of verdict "{2}", job "{3}" as expected'.format(
                        'more' if len(report['marks']) > 1 else 'less', i, verdict, job))

        for mark_id in job_verdict_result['marks'].keys():
            if all(not mark_in(mark_id, verdict_type, verdict) for verdict_type in
                    ('ideal verdicts', 'current verdicts')):
                new_marks.append(mark_id)
            else:
                matched_marks.append(mark_id)

                for report in job_verdict_result['reports']:
                    if mark_id in report['marks']:
                        # For unsafe marks there are similarities for each pair or unsafe-mark.
                        dif = report['marks'][mark_id] if verdict == 'unsafes' else 1

                        if mark_in(mark_id, 'ideal verdicts', verdict) and \
                            (regr_test_results['ideal verdicts'][verdict][mark_id] > 0 or \
                            not mark_in(mark_id, 'current verdicts', verdict)):
                            target_verdict = 'ideal verdicts'
                        else:
                            target_verdict = 'current verdicts'

                        regr_test_results[target_verdict][verdict][mark_id] -= dif

        # Combine marks from both types of verdicts to get unmatched marks if so.
        regr_test_marks = []
        for verdict_type in ('ideal verdicts', 'current verdicts'):
            if verdict in regr_test_results.get(verdict_type, []):
                regr_test_marks.extend(list(regr_test_results[verdict_type][verdict]))

        if regr_test_marks:
            unmatched_marks = set(regr_test_marks) - set(matched_marks)
            if unmatched_marks:
                error_msgs.append(
                    'There are unmatched marks for verdict "{0}", job "{1}": '.format(verdict, job) +
                    ', '.join(unmatched_marks))

        for verdict_type in ('ideal verdicts', 'current verdicts'):
            if verdict in regr_test_results.get(verdict_type, []):
                for mark_id in regr_test_results[verdict_type][verdict]:
                    if regr_test_results[verdict_type][verdict][mark_id]:
                        error_msgs.append(
                            'There are {0} associations for mark "{1}" of verdict "{2}", '
                            'job "{3}" as expected'
                                .format('more' if regr_test_results[verdict_type][verdict][mark_id] < 0
                                        else 'less', mark_id, verdict, job))

        if new_marks:
            error_msgs.append(
                'There are new marks for verdict "{0}", job "{1}": '
                .format(verdict, job) + ', '.join(new_marks))

    return error_msgs


def main(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description="Run asm parser")
    parser.add_argument('--job_file', type=str, help='Job file to run')

    args = parser.parse_args(args)
    if not args.job_file:
        error(logger, 'No configuration file specified')

    error_msgs = []
    logger = get_logger(None)
    # Decide testing/validation jobs and obtain their results.
    job_versions_solution_results = {}

    with open(args.job_file) as fp:
        jobs = yaml.safe_load(fp)

    # Compare results with previous ones. Gather all mismatches.
    # with open('presets/marks/previous_regression_testing_results.yaml') as fp:
    #     regr_test_results = yaml.safe_load(fp)
    with open('presets/marks/previous regression testing results.json') as fp:
        regr_test_results = json.load(fp)

    for job in jobs['jobs']:
        if job['id'] not in regr_test_results:
            error_msgs.append('There are new testing/validation jobs with unknown previous results: ' + ', '.join(job))
        else:
            results = run_job(job, logger)
            job_versions_solution_results[job['id']] = results
            logger.info('Compare results for job "{0}"'.format(job['id']))
            error_msgs.extend(compare_results(job['id'], regr_test_results[job['id']], results))

        if error_msgs:
            error(logger, '\n'.join(error_msgs))

    # This file will be attached to e-mail.
    with open('job-versions-solution-results.yaml', 'w') as fp:
        yaml.dump(job_versions_solution_results, fp)

    # Execute unit tests for OpenStack deployment.
    if False:
        try:
            _execute_cmd(logger, 'pytest', '-x', '-s', os.path.join('src', 'tests', 'test_openstack.py'))
            logger.info('Unit tests for OpenStack deployment passed')
        except subprocess.CalledProcessError:
            error_msgs.append('Unit tests for OpenStack deployment failed')
    else:
        logger.info('Unit tests for OpenStack deployment were skipped')

    if error_msgs:
        error(logger, '\n'.join(error_msgs))


if __name__ == "__main__":
    main(sys.argv[1:])
