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

def run_job(job, logger, credentials):
    logger.info('Start decision of job {0} ({1})'.format(job['name'], job['id']))
    started_job_solution_str = execute_cmd(logger, 'venv/bin/klever-start-preset-solution',
                                            '--rundata', 'ci-config/validation job decision configuration.json'
                                            if job.get('validation')
                                            else 'ci-config/job decision configuration.json',
                                            job['id'], *credentials, get_output=True)

    m = re.search(r': (.+)', started_job_solution_str)
    if not m:
        raise RuntimeError("Unexpected output '{0}'".format(started_job_solution_str))

    # Get identifier of job version which solution was started.
    job_version = m.group(1)

    # Wait till job will be decided somehow.
    while True:
        time.sleep(5)
        execute_cmd(logger, 'venv/bin/klever-download-progress', '-o',
                    'job-version-solution-progress.json', job_version, *credentials)

        with open('job-version-solution-progress.json') as fp:
            job_version_solution_progress = json.load(fp)

        if int(job_version_solution_progress['status']) > 2:
            break

    # Store obtained verification results.
    execute_cmd(logger, 'venv/bin/klever-download-results',
                '-o', 'job-version-solution-results.json', job_version, *credentials)
    with open('job-version-solution-results.json') as fp:
        return json.load(fp)


def main(args=sys.argv[1:]):
    parser = argparse.ArgumentParser(description="Run asm parser")
    parser.add_argument('--job_file', type=str, help='Job file to run')

    args = parser.parse_args(args)
    if not args.job_file:
        error(logger, 'No configuration file specified')

    error_msgs = []
    logger = get_logger(None)
    # Decide testing/validation jobs and obtain their results.
    credentials = ('--host', 'localhost:8998', '--username', 'manager', '--password', 'manager')
    job_versions_solution_results = {}

    with open(args.job_file) as fp:
        jobs = yaml.safe_load(fp)

    # Compare results with previous ones. Gather all mismatches.
    with open('presets/marks/previous regression testing results.json') as fp:
        regr_test_results_all = json.load(fp)
    
    regr_test_results = {}

    for job in jobs['jobs']:
        regr_test_results[job['id']] = regr_test_results_all[job['id']]
        job_versions_solution_results[job['id']] = run_job(job, logger, credentials)

    if not job_versions_solution_results:
        error(logger, 'No test found for current launch')

    # This file will be attached to e-mail.
    with open('job-versions-solution-results.json', 'w') as fp:
        json.dump(job_versions_solution_results, fp, sort_keys=True, indent=4)

    new_jobs = []
    failed_jobs = []
    for job, job_version_solution_results in job_versions_solution_results.items():
        logger.info('Compare results for job "{0}"'.format(job))

        if job not in regr_test_results:
            new_jobs.append(job)
            continue

        status = int(job_version_solution_results['status'])
        if status != 3:
            failed_jobs.append(job)

        new_marks = {}
        matched_marks = {}
        for verdict in ('safes', 'unsafes', 'unknowns'):
            for i, report in enumerate(job_version_solution_results[verdict]['reports']):
                # Do not hurt if there are several associated unknown marks for unknowns since this is quite naturally.
                if len(report['marks']) != 1 and (verdict != 'unknowns' or len(report['marks']) < 1):
                    error_msgs.append(
                        'There are {0} associations for report "{1}" of verdict "{2}", job "{3}" as expected'.format(
                            'more' if len(report['marks']) > 1 else 'less', i, verdict, job))

            mark_ids = list(job_version_solution_results[verdict]['marks'].keys())
            for mark_id in mark_ids:
                if all(verdict_type not in regr_test_results[job]
                        or (verdict_type in regr_test_results[job] and (
                        verdict not in regr_test_results[job][verdict_type] or (
                        verdict in regr_test_results[job][verdict_type] and mark_id not in
                        regr_test_results[job][verdict_type][verdict]))) for verdict_type in
                        ('ideal verdicts', 'current verdicts')):
                    if verdict not in new_marks:
                        new_marks[verdict] = []

                    new_marks[verdict].append(mark_id)
                else:
                    if verdict not in matched_marks:
                        matched_marks[verdict] = []

                    matched_marks[verdict].append(mark_id)

                    for report in job_version_solution_results[verdict]['reports']:
                        for report_mark_id in report['marks']:
                            if report_mark_id == mark_id:
                                # For unsafe marks there are similarities for each pair or unsafe-mark.
                                dif = report['marks'][report_mark_id] if verdict == 'unsafes' else 1

                                if 'ideal verdicts' in regr_test_results[job] and \
                                        verdict in regr_test_results[job]['ideal verdicts'] and \
                                        mark_id in regr_test_results[job]['ideal verdicts'][verdict]:
                                    if regr_test_results[job]['ideal verdicts'][verdict][
                                        mark_id] > 0 or 'current verdicts' not in regr_test_results[
                                        job] or verdict not in regr_test_results[job][
                                        'current verdicts'] or mark_id not in \
                                            regr_test_results[job]['current verdicts'][verdict]:
                                        regr_test_results[job]['ideal verdicts'][verdict][mark_id] -= dif
                                    else:
                                        regr_test_results[job]['current verdicts'][verdict][mark_id] -= dif
                                else:
                                    regr_test_results[job]['current verdicts'][verdict][mark_id] -= dif

            # Combine marks from both types of verdicts to get unmatched marks if so.
            regr_test_marks = {}
            for verdict_type in ('ideal verdicts', 'current verdicts'):
                if verdict_type in regr_test_results[job] \
                        and verdict in regr_test_results[job][verdict_type]:
                    if verdict not in regr_test_marks:
                        regr_test_marks[verdict] = []

                    regr_test_marks[verdict].extend(list(regr_test_results[job][verdict_type][verdict]))

            if verdict in regr_test_marks:
                unmatched_marks = set(regr_test_marks[verdict]) - (
                    set(matched_marks[verdict]) if verdict in matched_marks else set())
                if unmatched_marks:
                    error_msgs.append(
                        'There are unmatched marks for verdict "{0}", job "{1}": '.format(verdict, job) +
                        ', '.join(unmatched_marks))

            for verdict_type in ('ideal verdicts', 'current verdicts'):
                if verdict_type in regr_test_results[job] and verdict in regr_test_results[job][verdict_type]:
                    for mark_id in regr_test_results[job][verdict_type][verdict]:
                        if regr_test_results[job][verdict_type][verdict][mark_id]:
                            error_msgs.append(
                                'There are {0} associations for mark "{1}" of verdict "{2}", '
                                'job "{3}" as expected'
                                    .format('more' if regr_test_results[job][verdict_type][verdict][mark_id] < 0
                                            else 'less', mark_id, verdict, job))

        for verdict in new_marks:
            error_msgs.append(
                'There are new marks for verdict "{0}", job "{1}": '
                .format(verdict, job) + ', '.join(new_marks[verdict]))

        del regr_test_results[job]

    if new_jobs:
        error_msgs.append('There are new testing/validation jobs with unknown previous results: ' + ', '.join(new_jobs))

    if regr_test_results:
        error_msgs.append('There are no more testing/validation jobs: ' + ', '.join(list(regr_test_results.keys())))

    if failed_jobs:
        error_msgs.append('Testing/validation jobs failed: ' + ', '.join(failed_jobs))

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
