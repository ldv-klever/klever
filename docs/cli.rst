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
In addition, it presents examples of using the corresponding Python API.

Setting Up Python API
---------------------

Prior to refer to the Python API you need to set up an interface object.
For default :ref:`local_deploy` it can be done in the following way::

    from klever.cli import Cli
    cli = Cli(host=f'{hostname_or_ip}:8998', username='manager', password='manager')

You should specify these host and credentials as corresponding command-line arguments for all commands as well.

Starting Solution of Verification Jobs
--------------------------------------

You can start solution of a verification job based on any preset verification job.
For this you should find out a corresponding identifier, **preset_job_id**, e.g. using Web UI.
For instance, Linux loadable kernel modules sample has identifier "c1529fbf-a7db-4507-829e-55f846044309".
Then you should run something like::

    klever-start-preset-solution --host $hostname_or_ip:8998 --username manager --password manager $preset_job_id

In the output of this command there are:

* **job_id** - an identifier of the created verification job.
* **decision_id** - an identifier of a first version of the created verification job which decision was started.

There are several command-line arguments that you can use: :option:`--rundata` and :option:`--replacement`.

.. option:: --rundata <job solution configuration file>

    If you need some non-standard settings for solution of the verification job, e.g. you have a rather powerful machine
    and you want to use more parallel workers to generate verification tasks to speed up the complete process, you can
    provide a specific job solution configuration file.
    We recommend to develop an appropriate solution configuration using Web UI first and then you can download this file
    at the verification job page (e.g. :menuselection:`Decision --> Download configuration`).

.. option:: --replacement <JSON string or JSON file>

    If you need to add some extra files in addition to files of the preset verification job or you want to replace some
    of them, you can describe corresponding changes using this option.
    For instance, you can provide a specific :ref:`Klever build base <klever_build_bases>` and refer to it in
    **job.json**.
    In this case the value for this option may look like::

        '{"job.json": "job.json", "loadable kernel modules sample.tar.gz": "loadable kernel modules sample.tar.gz"}'

    File **job.json** and archive **loadable kernel modules sample.tar.gz** should be placed into the current working
    directory.

The corresponding Python API calls look as follows::

    job_id = cli.create_job(preset_job_id)[1]
    decision_id = cli.start_job_decision(job_id)[1]

For *start_job_decision* there are arguments *rundata* and *replacement* corresponding to :option:`--rundata` and
:option:`--replacement`.

Waiting for Solution of Verification Job
----------------------------------------

Most likely you will need to wait for solution of the verification job whatever it will be successful or not.
For this purpose you can execute something like::

    klever-download-progress --host $hostname_or_ip:8998 --username manager --password manager -o progress.json $decision_id

until **status** in *progress.json* will be more than 2.

The appropriate invocation of the Python API may look like::

    while True:
      time.sleep(5)
      progress = cli.decision_progress(decision_id)

      if int(progress['status']) > 2:
        break

Obtaining Verification Results
------------------------------

You can get verification results by using such the command::

    klever-download-results --host $hostname_or_ip:8998 --username manager --password manager -o results.json $decision_id

or via the following Python API::

    results = cli.decision_results(decision_id)

Then you can inspect file **results.json** or dictionary **results** somehow.
Though, as it was noted, most likely you will need to analyze these results manually via Web UI.
