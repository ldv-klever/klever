.. Copyright (c) 2021 ISP RAS (http://www.ispras.ru)
   Ivannikov Institute for System Programming of the Russian Academy of Sciences
   Licensed under the Apache License, Version 2.0 (the "License");
   you may not use this file except in compliance with the License.
   You may obtain a copy of the License at
       http://www.apache.org/licenses/LICENSE-2.0
   Unless required by applicable law or agreed to in writing, software
   distributed under the License is distributed on an "AS IS" BASIS,
   WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
   See the License for the specific language governing permissions and
   limitations under the License.

.. _cli:

CLI
===

Klever supports a command-line interface for starting solution of verification jobs, for getting progress of their
solution, etc.
One can use CLI to automate usage of Klever, e.g. within CI.
You should note that CLI is not intended for generation of :ref:`klever_build_bases` and expert assessment of
verification results.

This section describes several most important commands and the common workflow.
We used Python 3.7 to describe commands, but you can levearage any appropriate language.

Credentials
-----------

All commands require credentials for execution.
For default :ref:`local_deploy` they look like::

    credentials = ('--host', 'localhost:8998', '--username', 'manager', '--password', 'manager')

Starting Solution of Verification Jobs
--------------------------------------

You can start solution of a verification job based on any preset verification job.
For this you should find out a corresponding identifier, **preset_job_id**, e.g. using Web UI.
For instance, Linux loadable kernel modules sample has identifier "c1529fbf-a7db-4507-829e-55f846044309".
Then you should run something like::

    ret = subprocess.check_output(('klever-start-preset-solution', preset_job_id, *credentials)).decode('utf8').rstrip()
    job_id = ret[ret.find(': ') + 2:]

After this **job_id** will keep an identifier of the created verification job (strictly speaking, it will be an
identifier of a first version of the created verification job).

There are several command-line arguments that you can want to use: :option:`--rundata` and :option:`--replacement`.

.. option:: --rundata <job solution configuration file>

    If you need some non-standard settings for solution of the verification job, e.g. you have a rather powerful machine
    and you want to use more parallel workers to generate verification tasks to speed up the complete process, you can
    provide a specific job solution configuration file.
    We recommend to develop an appropriate solution configuration using Web UI first and then you can download this file
    at the verification job page (e.g. :menuselection:`Decision --> Download configuration`).

.. option:: --replacement <JSON string or JSON file>

    If you need to add some extra files in addition to files of the preset verification job or you want to replace some
    of them, you can describe corresponding changes using this command-line option.
    For instance, you can provide a specific :ref:`Klever build base <klever_build_bases>` and refer to it in
    **job.json**.
    In this case the value for this option may look like::

        '{"job.json": "job.json", "loadable kernel modules sample.tar.gz": "loadable kernel modules sample.tar.gz"}'

    File **job.json** and archive **loadable kernel modules sample.tar.gz** should be placed into the current working
    directory.

Waiting for Solution of Verification Job
----------------------------------------

Most likely you will need to wait for solution of the verification job whatever it will be sucessfull or not.
For this purpose you can execute something like::

    while True:
      time.sleep(5)
      subprocess.check_call(('klever-download-progress', '-o', 'progress.json', job_id, *credentials))

      with open('progress.json') as fp:
        progress = json.load(fp)

      if int(progress['status']) > 2:
        break

Obtaining Verification Results
------------------------------

You can download verification results by using such the command::

    subprocess.check_call(('klever-download-results', '-o', 'results.json', job_id, *credentials))

Then you can inspect file **results.json** somehow.
Though, as it was noted, most likely you will need to analyze these results manually via Web UI.
