.. Copyright (c) 2020 ISP RAS (http://www.ispras.ru)
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

Developer Documentation
=======================

How to Write This Documentation
-------------------------------

This documentation is created using `Sphinx <http://sphinx-doc.org>`__ from
`reStructuredText <http://docutils.sourceforge.net/rst.html>`__ source files.
To improve existing documentation or to develop the new one you need to read at least the following chapters of the
`Sphinx documentation <http://sphinx-doc.org/contents.html>`__:

#. `Defining document structure <http://sphinx-doc.org/tutorial.html#defining-document-structure>`__.
#. `Adding content <http://sphinx-doc.org/tutorial.html#adding-content>`__.
#. `Running the build <http://sphinx-doc.org/tutorial.html#running-the-build>`__.
#. `reStructuredText Primer <http://sphinx-doc.org/rest.html>`__.
#. `Sphinx Markup Constructs <http://sphinx-doc.org/markup/index.html>`__.
#. `Sphinx Domains <http://sphinx-doc.org/domains.html>`__ (you can omit language specific domains).

Please, follow these advises:

#. Do not think that other developers and especially users are so smart as you are.
#. Clarify ambiguous things and describe all the details without missing anything.
#. Avoid and fix misprints.
#. Write each sentence on a separate line.
#. Do not use blank lines except it is required.
#. Write a new line at the end of each source file.
#. Break sentences longer than 120 symbols to several lines if possible.

To develop documentation it is recommended to use some visual editor.

.. warning:: Please do not reinvent the wheel!
   If you are a newbie then examine carefully the existing documentation and create the new one on that basis.
   Just if you are a guru then you can suggest to improve the existing documentation.

Using Git Repository
--------------------

Klever source code resides in the `Git <https://git-scm.com/>`__ repository.
There is plenty of very good documentation about Git usage.
This section describes just rules specific for the given project.

Update
^^^^^^

#. Periodically synchronize your local repository with the main development repository (it is available just internally
   at ISP RAS)::

    branch $ git fetch origin
    branch $ git remote prune origin

   .. note:: This is especially required when you are going to create a new branch or to merge some branch to the master
             branch.

#. Pull changes if so::

    branch $ git pull --rebase origin branch

   .. warning:: Forget about pulling without rebasing!

#. Resolve conflicts if so.

Fixing Bugs and Implementing New Features
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. One must create a new branch to fix each individual bug or implement a new feature::

    master $ git checkout -b fix-conf

   .. warning:: Do not intermix fixes and implementation of completely different bugs and features into one branch.
                Otherwise other developers will need to wait or to make some tricky things like cherry-picking and
                merging of non-master branches.
                Eventually this can lead to very unpleasant consequences, e.g. the master branch can be broken because
                of one will merge there a branch based on another non working branch.

#. Push all new branches to the main development repository.
   As well re-push them at least one time a day if you make some commits::

    fix-conf $ git push origin fix-conf

#. Merge the master branch into your new branches if you need some recent bug fixes or features::

    fix-conf $ git merge master

   .. note:: Do not forget to update the master branch from the main development repository.

   .. note:: Do not merge remote-tracking branches.

#. Ask senior developers to review and to merge branches to the master branch when corresponding bugs/features are
   fixed/implemented.

#. Delete merged branches::

    master $ git branch -d fix-conf

Releases
--------

Generally we follow the same rules as for development of the Linux kernel.

Each several months a new release will be issued, e.g. 0.1, 0.2, 1.0.

Just after this a merge window of several weeks will be opened.
During the merge window features implemented after a previous merge window or during the given one will be merged to
master.

After the merge window just bug fixes can be merged to the master branch.
During this period we can issue several release candidates, e.g. 1.0-rc1, 1.0-rc2.

In addition, after issuing a new release we can decide to support a stable branch.
This branch will start from a commit corresponding to the given release.
It can contain just bug fixes relevant to an existing functionality and not to a new one which is supported within a
corresponding merge window.

Updating List of Required Python Packages
-----------------------------------------

To update the list of required Python packages first you need to install Klever package from scratch in the newly
created virtual environment without using the old `requirements.txt` file.
Run the following commands within :term:`$KLEVER_SRC`::

    $ python3 -m venv venv
    $ source venv/bin/activate
    $ pip install --upgrade pip wheel setuptools setuptools_scm
    $ pip install .

This will install latest versions of required packages.
After confirming that Klever works as expected, you should run the following command within :term:`$KLEVER_SRC`::

    $ python -m pip freeze | grep -v 'klever' > requirements.txt

Updated list of requirements will be saved and should be committed to the repository afterwards.

Besides, you should also update the list of required Python packages for OpenStack deployment.
For this purpose you need to run the following commands after executing commands above::

    $ pip install ".[openstack]"
    $ python -m pip freeze | grep -v 'klever' > requirements-openstack.txt

At last you should specify actual versions of Python packages in :file:`docs/requirements.txt`.
Note, that Sphinx 4.4.0 requires docutils < 0.18.

.. _test_build_bases_generation:

How to generate build bases for testing Klever
----------------------------------------------

Most likely you can get actual, prepared in advance build bases for testing Klever from
*ldvuser@ldvdev:build-bases/build-bases.tar.xz* (this works just within the ISP RAS local network).

To generate build bases for testing Klever you need to execute following commands within :term:`$KLEVER_SRC`::

   $ docker build -t build-bases -f Dockerfile.build-bases .
   $ docker create --name dummy build-bases
   $ docker cp dummy:/usr/src/build-bases.tar.xz build\ bases/
   $ docker rm dummy

After that the archive with generated build bases will be located ad :file:`build bases/build-bases.tar.xz`.

Besides, you can follow the following steps:

#. Install Klever locally for development purposes according to the user documentation (see :ref:`deploy`).
#. Create a dedicated directory for sources and build bases and move to it.
   Note that there should be quite much free space.
   We recommend at least 100 GB.
   In addition, it would be best of all if you will name this directory "build bases" and create it within the root of
   the Klever Git repository (this directory is not tracked by the repository).
#. Clone a Linux kernel stable Git repository to *linux-stable* (scripts prepare build bases for different versions of
   the Linux kernel for which the Git repository serves best of all), e.g.::

    $ git clone https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/ linux-stable

   You can use alternative sources of the Git repository, if the above one is not working well and fast enough:

   #. https://kernel.googlesource.com/pub/scm/linux/kernel/git/stable/linux-stable
   #. https://github.com/gregkh/linux

#. Read notes regarding the compiler after the end of this list.
#. Run the following command to find out available descriptions of build bases for testing Klever::

    $ klever-build -l

#. Select appropriate build bases descriptions and run the command like below::

    $ klever-build "linux/testing/requirement specifications" "linux/testing/common models"

#. Wait for a while.
   Prepared build bases will be available within directory "build bases".
   Note that there will be additional identifiers, e.g. "build bases/linux/testing/6e6e1c".
   These identifiers are already specified within corresponding preset verification jobs.
#. You can install prepared build bases using deployment scripts, but it is boring.
   If you did not follow an advice regarding the name and the place of the dedicated directory from item 2, you can
   create a symbolic link with name "build bases" that points to the dedicated directory within the root of the Klever
   Git repository.

Providing an appropriate compiler
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Most of build bases for testing Klever could be built using GCC 4.8 on Debian or Ubuntu.
Otherwise there is an explicit division of build bases descriptions, e.g.:

* linux/testing/environment model specifications/gcc48
* linux/testing/environment model specifications/gcc63

(the former requires GCC 4.8 while the latter needs GCC 6.3 at least).

That's why you may need to get GCC 4.8 and make it available through PATH.
Users of some other Linux distributions, e.g. openSUSE 15.1, can leverage the default compiler for building all build
bases for testing Klever.

The simplest way to get GCC 4.8 on Ubuntu is to execute the following commands::

    $ sudo apt update
    $ sudo apt install gcc-4.8
    $ sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-7 70
    $ sudo update-alternatives --install /usr/bin/gcc gcc /usr/bin/gcc-4.8 48
    $ sudo update-alternatives --config gcc

(after executing the last command you need to select GCC 4.8; do not forget to make v.v. after preparing build bases!)

Generating Bare CPAchecker Benchmarks
-------------------------------------

Development of Klever and development of CPAchecker are not strongly coupled.
Thus, verification tasks that are used for testing/validation of Klever including different versions and configurations
of CPAchecker as back-ends may be useful to track regressions of new versions of CPAchecker.
This should considerably simplify updating CPAchecker within Klever (this process usually involves a lot of various
activities both in Klever and in CPAchecker; these activities can take enormous time to be completed that complicates
and postpones updates considerably).
In addition, this is yet another test suite for CPAchecker.
In contrast to other test suites this one likely corresponds to the most industry close use cases.

One can (re-)generate bare CPAchecker benchmarks almost automatically.
To do this it is recommended to follow next steps:

#. Clone `<https://gitlab.com/sosy-lab/software/ldv-klever-benchmarks.git>`__ or
   `<git@gitlab.com:sosy-lab/software/ldv-klever-benchmarks.git>`__ once.
#. After some changes within Klever specifications, configurations and test cases you need to solve appropriate
   verification jobs.
   To avoid some non-determinism it is better to use the same machine, e.g. LDV Dev, to do this.
   Though particular verification jobs to be solved depend on changes made, in ideal, it is much easier to consider all
   verification jobs at once to avoid any tricky interdependencies (even slight improvements or fixes of some
   specifications may result in dramatic and unexpected changes in some verification results).
#. Download archives with verifier input files for each solved verification jobs to the root directory of the cloned
   repository.
#. Run "python3 make-benchs.py" there.
#. Estimate changes in benchmarks and verification tasks (there is not any formal guidance).
   If you agree with these changes, then you need to commit them and to push to the remote.
   After that one may expect that new commits to trunk of the CPAchecker repository will be checked for regressions
   against an updated test suite.

Using PyCharm IDE
-----------------

To use PyCharm IDE for developing Klever follow the following steps.

Installation
^^^^^^^^^^^^

#. Download PyCharm Community from `<https://www.jetbrains.com/pycharm/download/>`_ (below all settings are given for
   version 2018.8.8, you have to adapt them for your version by yourself).
#. Follow installation instructions provided at that site.

Setting Project
^^^^^^^^^^^^^^^

At the "Welcome to PyCharm" window:

#. Specify your preferences.
#. :menuselection:`Open`.
#. Specify the absolute path to directory :term:`$KLEVER_SRC`.
#. :menuselection:`OK`.

Configuring the Python Interpreter
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

#. :menuselection:`File --> Settings --> Project: Klever --> Project Interpreter --> Settings --> Show all...`.
#. Select the Python interpreter from the Klever Python virtual environment.
#. :menuselection:`OK`.
#. Select the added Python interpreter from the list and press :kbd:`Enter`.
#. Input *Python 3.10 (klever)* in field :guilabel:`name`.
#. :menuselection:`OK`.
#. For the rest projects select *Python 3.10 (klever)* in field :guilabel:`Project Interpreter`.

Setting Run/Debug Configuration
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Common run/debug configurations are included into the Klever project.
Common configurations with names starting with **$** should be copied to configurations with names without **$** and
adjusted in accordance with instructions below.
If you want to adjust configurations with names that not starting with **$** you also have to copy them before.

#. :menuselection:`Run --> Edit Configurations...`.

Klever Bridge Run/Debug Configuration
"""""""""""""""""""""""""""""""""""""

.. note:: This is available just for PyCharm Professional.

* Specify *0.0.0.0* in field :guilabel:`Host` if you want to share your Klever Bridge to the local network.
* Specify your preferred port in field :guilabel:`Port`.

.. note:: To make your Klever Bridge accessible from the local network you might need to set up your firewall
          accordingly.

Klever Core Run/Debug Configuration
"""""""""""""""""""""""""""""""""""

This run/debug configuration is only useful if you are going to debug Klever Core.

* Extend existing value of environment variable :envvar:`PATH` so that CIF (:file:`cif` or :file:`compiler`),
  Aspectator (:file:`aspectator`) and CIL (:file:`toplevel.opt`) binaries could be found (edit value of field
  :guilabel:`Environment variables`).
* Specify the absolute path to the working directory in field :guilabel:`Working directory`.

   .. note:: Place Klever Core working directory somewhere outside the main development repository.

   .. note:: Klever Core will search for its configuration file :file:`core.json` in the specified working directory.
             Thus, the best workflow to debug Klever Core is to set its working directory to the one created previously
             when it was run without debugging.
             Besides, you can provide this file by passing its name as a first parameter to the script.

Documentation Run/Debug Configuration
"""""""""""""""""""""""""""""""""""""

Specify another representation of documentation in field :guilabel:`Command` if you need it.

Testing
^^^^^^^

Klever Bridge Testing
"""""""""""""""""""""

.. note:: This is available just for PyCharm Professional.

#. :menuselection:`Tools --> Run manage.py Task...`::

    manage.py@bridge > test

.. note:: To start tests from console::

    $ cd bridge
    $ python3 manage.py test

.. note:: Another way to start tests from console::

    $ python3 path/to/klever/bridge/manage.py test bridge users jobs reports marks service

.. note:: The test database is created and deleted automatically.
          If the user will interrupt tests the test database will preserved and the user will be asked for its deletion
          for following testing.
          The user should be allowed to create databases (using command-line option *--keedb* does not help).

.. note:: PyCharm has reach abilities to analyse tests and their results.

Additional documentation
^^^^^^^^^^^^^^^^^^^^^^^^

A lot of useful documentation for developing Django projects as well as for general using of the PyCharm IDE is
available at the official `site <https://www.jetbrains.com/pycharm/documentation/>`__.

Using Visual Studio Code
------------------------

Klever includes quite much C stuff such as models and tests.
You may want to use VS Code to develop it since VS Code can find errors, suggest proper entity names and so on.
First of all you need to install an appropriate extension for support of C/C++.

There is a basic configuration for VS Code in Klever already.
It excludes some directories from search and indexing, refers Klever directories with auxiliary headers and so on.
If you use headers (functions, types, macros, etc.) from your project within models and tests, you need to configure
VS Code appropriately.
This strongly depends on particular project and its build process.
We suggest to refer headers that are placed to directory *Storage* of the Clade's build base since there will be only
those ones that are suitable for those configuration and architecture of the target program, that you are going to
verify.
For instance, for common models, requirement specifications and their tests you can specify following directories
to search for headers as a value of option *C_Cpp.default.includePath* for your local user's settings:

* /abs_path_to_clade_build_base/Storage/src/linux-5.12-rc3/include/
* /abs_path_to_clade_build_base/Storage/src/linux-5.12-rc3/arch/x86/include/
* /abs_path_to_clade_build_base/Storage/src/linux-5.12-rc3/arch/x86/include/uapi/
* /abs_path_to_clade_build_base/Storage/src/linux-5.12-rc3/arch/x86/include/generated/

Moreover, to resolve some conflicts you may have to set "CONFIG_SMP" as a value of option *C_Cpp.default.defines*.
Please, do not include project-specific settings to the common settings of VS Code stored within directory *.vscode*.

Extended Violation Witness Format
---------------------------------

The `original format of violation witnesses <https://github.com/sosy-lab/sv-witnesses>`__ is intended primarily for
automatic validation.
Each violation witness can describe a subset of possible execution paths and lack some important details.
This hinders their manual analysis by experts.

We suggest the extended format of violation witnesses to enhance their visualization and assessment capabilities.
This format requires an extended violation witness to represent a single error path as accurate as possible, i.e. it
should refer all expressions, statements and declarations starting from an entry point and up to a found violation as
well as all global variable declarations.
Besides, extended violation witnesses should mandatory use *enterFunction* and *returnFromFunction* tags for all
functions that are called along the error path and have definitions.

To distinguish declarations from statements and expressions, especially, to separate global variable declarations from
the entry point, we suggest to introduce an additional data tag *declaration*.
Its value should be *true* for all edges corresponding to global and local declarations.
Its default value used for all other edges implicitly should be *false*.

One more extension is intended for adding important internal information from verification tools to violation
witnesses.
For instance, when checking memory safety verification tools can point out places where leaked memory is allocated.
The corresponding data tag is *note*.
Its value should has the following format::

    level="N" hide="true|false" value="Some meaningful text"

*N* sets the importance of the note.
It should be in range from 0 to 3 where 0 should be used just for edges corresponding to found violations.
Level 1 should be used for vital notes since these notes will be shown by default and they will be used for obtaining
*error trace patterns* used for automatic assessment of similar violation witnesses.
All levels of notes will be specially highlighted at visualization.
Attribute *hide* controls whether notes should be shown together with corresponding edges (in case when *hide* is
*false*) or without it (otherwise).
Edges can be omitted when notes represent enough information about them in their attribute *value*.
The example of this data tag value is as follows::

    level="0" hide="false" value="Memory leak of calloc_ID13 is detected"

Verification tools can provide multiple *note* data tags per an edge.

Thus, the extended format of violation witnesses does extend the existing format of violation witnesses.
Extended violation witnesses can be even validated like non-extended ones.

Error Trace Format
------------------

We suggest converting violation witnesses in the extended format represented above to error traces that are more
convenient for visualization and assessment purposes.
Error traces should be represented as JSON files with the following content:

.. code-block:: json

    {
        "format": 1,
        "files": [
            "filename1",
            "filename2",
            "..."
        ],
        "global variable declarations": [
            {
                "file": 0,
                "line": 1,
                "source": "struct module x;"
            },
            {
                "file": 0,
                "line": 2,
                "source": "static ldv_counter = 1;",
                "notes": [
                    {
                        "level": 1
                        "text": "Initialize counter to zero"
                    }
                ],
                "hide": true
            },
            {
            }
        ],
        "trace": "NodeObject"
    }

*format* indicates a current version of the error trace format.
For all changes in syntax and especially semantics of the represented data it should be changed.

*files* lists all filenames referred by the error trace.
Below particular files are represented as indexes in this array.
This is necessary for optimization purposes since there may be very many edges corresponding to different files that
can have rather long paths.

For global variable declarations *file*, *line* and *source* are mandatory attributes.
Their meaning is quite obvious.
*notes* and *hide* correspond to entities from the extended violation witnesses straightforwardly.
Below we present a bit more details on these attributes.

*NodeObject* represents the error path (error trace) starting from the entry point and finishing at the detected
violation.
It is a JSON object with following attributes:

* *type* - one of "thread", "action", "declarations", "declaration", "statement" and "function call".
* *thread* - a thread identifier.
  This attribute is mandatory for objects of type "thread".
* *file* - an index in the array of files presented above.
  This attribute is mandatory for objects of types "action", "declaration", "statement" and "function call".
* *line* - a line number in this file.
  This attribute is mandatory for the same objects as *file*.
* *source* - a piece of the source code corresponding to a violation witness edge.
  This attribute is mandatory for objects of types "declaration", "statement" and "function call".
* *highlight* - highlighting for a given piece of the source code.
  This attribute can be set for the same objects as *source*.
  Its value is an array of arrays each containing a highlight class that influences visualization, a start offset and
  an end offset of a corresponding entity.
  All offsets should be in a *source* length range, they should not overlap and the end offset should be greater than
  the start offset.
* *condition* - either true or false depending on a corresponding edge represents a conditional statement or not
  respectively.
  This attribute can be sef for objects of types "statement" and "function call".
* *assumption* - verification tool assumptions coinciding with a value of *assumption* data tag.
  This attribute can be sef for objects of types "statement" and "function call".
* *display* - a text replacing *source*, e.g. instead of a complete function call statement just a function name can
  be shown if it is stored as a value of this attribute.
  This attribute is mandatory for objects of types "action" and "function call".
  Also, it can be set for objects of types "declaration" and "statement".
* *relevant* - either true or false that denotes actions that are relevant and irrelevant for creating error trace
  patterns.
  This attribute is mandatory for objects of type "action".
  By default its value is false.
* *notes* - a list of notes like demonstrated above.
  This attribute is mandatory for objects of types "declaration", "statement" and "function call".
* *hide* - either true of false that correspondingly hides or shows a corresponding *source* or *display*.
  This attribute is mandatory for the same objects as *notes*.
  By default its value is false.
* *children* - a list of elements each of type *NodeObject*.
  This attribute is mandatory for objects of types "thread", "action", "declarations" and "function call".

The first *NodeObject* should have the *thread* type.

Code Coverage Format
--------------------

We suggest to convert code coverage reports from verification tools to the more appropriate form for their
visualization.
Converted code coverage reports should be represented as JSON files.
There are should be JSON files for all source files that were covered somehow as well as one file per a verification
task with statistics.
Code coverage for individual source files should be placed to files *path/to/src_file.cov.json* and they should have the
following content:

.. code-block:: json

    {
        "format": 1,
        "line coverage": {
            "1": 4,
            "3": 7,
            "...": "..."
        },
        "function coverage": {
            "1": 1,
            "17": 0,
            "...": "..."
        },
        "notes": {
            "19": {
                "kind": "Verifier assumption",
                "text": "Inline Assembler is ignored"
            },
            "51": {
                "kind": "Environment modelling hint",
                "text": "Function \"driver_release\" may be called within context of \"driver_probe\" and \"driver_disconnect\" entry points"
            },
            "...": "..."
        }
    }

*format* means the same as the error trace format considered above.

*line coverage* and *function coverage* shows the number of states for corresponding lines of code.
For functions these lines of code coincide with places where they are defined.
The number of states reflect time spent for verification of lines and functions to some extent.

*notes* enumerate hints from verification tools or Klever itself for corresponding lines of code.
Each such hint can have a random text and one of predefined kinds.
For each kind a dedicated style will be used at visualization.

Code coverage statistics should be put to file *coverage.json* of the following content:

.. code-block:: json

    {
        "format": 1,
        "coverage statistics": {
            "path/to/src": [100, 1000, 5, 10],
            "...": []
        },
        "most covered lines": [
              "path/to/src:333",
              "path/to/another/src:33",
              "path/to/src:233",
              "..."
        ]
    }

*format* means the same as the error trace format considered above.

*coverage statistics* represents the number of covered lines, the number of lines that could be covered potentially,
the number of covered functions and the number of functions that could be covered potentially for corresponding source
files.

*most covered lines* enumerates source files and lines within them that were covered most times.

The same format is appropriate for representing code coverage for the whole program independently for each requirements
specification that is also supported by Klever.
