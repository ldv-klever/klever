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

.. _dev_env_specs:

Development of Environment Specifications
=========================================

Libraries, user inputs, other programs, etc. constitute an environment that can influence a program execution. It is necessary to provide an :term:`environment model <Environment model>`.  which represents certain assumptions about the environment to verify any program:

* It should contain models of undefined functions which the program calls during execution and which can influence verification results.
* It should correctly initialize external global variables.
* It should contain an entry-point function for a verification tool to start its analysis from it. 
 
User-space programs have the main function that can be used as an entry point, but operating systems and other system software require adding an artificial one.

Our experience shows that bug-finding is possible even without accurate environment models. Still, precise environment models help to improve code coverage and avoid false alarms. It is crucial to provide the accurate environment model considering the specifics of checked requirements and programs under verification to achieve high-quality verification results. It becomes even more essential to provide the appropriate environment model to avoid missing faults and false alarms verifying program fragments.

Our experience shows that bug-finding is possible even without accurate environment models. Still, precise environment models help to improve code coverage and avoid false alarms. It is crucial to provide the accurate environment model considering the specifics of checked requirements and programs under verification to achieve high-quality verification results. It becomes even more essential to provide the appropriate environment model to avoid missing faults and false alarms verifying :term:`program fragments <Program fragment>`.

Environment Model Generator
^^^^^^^^^^^^^^^^^^^^^^^^^^^

The environment models generation step follows the program decomposition. Provided program is decomposed into separate independent program fragments. Each program fragment consists of several C source files. We call these files below program files.

EMG is a Klever component (plugin) that generates an environment model for a single provided program fragment. It is highly configurable and extendable, so a user needs to prepare its proper configuration to verify a new program. 

A JSON file with the requirement specifications base has a section with templates. Such templates contain a plugins entry that lists the configuration of different plugins to run. The EMG should always be the first one. See the example in :file:`presets/jobs/specification/Linux.json` in :term:`$KLEVER_SRC`:

.. code-block:: python

    {
        "templates": {
        "loadable kernel modules and kernel subsystems": {
        "plugins": [
            {
                "name": "EMG",
                "options": {
                    "generators options": [
                        {"linuxModule": {}},
                        {"linuxInsmod": {}},
                        {"genericManual": {}}
                    ],
                    "translation options": {
                        "allocate external": false
                    }
                }
            },
            ...
        ]
    }

The member with the **options** name contains the EMG configuration. There are descriptions of supported configuration parameters in the following sections of the document. 

EMG generates an environment model as the *main C file* and several aspect files intended for weaving their content to program files. We refer to these output files as aspect files. Each aspect file contains the code to add at the beginning of a program file or its end and a description of function calls and macros to replace with models. 

EMG generates environment models using the provided source code given as a project build base and specifications. Specifications are C files or JSON files with models in C or DSL languages. We distinguish specifications and environment models:

* The environment model is a file in an intermediate EMG notation or in C. The former is a file in the internal representation which is called an *intermediate environment model (IEM)*. The former is called the *final environment model (FEM)*. 
* Environment model specifications can describe IEMs for specific program fragments, models’ templates, parts, or even configuration parameters. Specifications are always prepared or modified by hand and provided as input to EMG.

The Klever presets directory has the “specifications” directory. It contains all specifications for different programs and components. EMG does not require pointing to specific files at providing specifications. It searches for all specifications in the directory and applies only relevant ones. Files of specifications for the EMG plugin have a particular naming policy. Their names always end with a suffix that distinguishes their utilization. These suffixes are described below.


EMG Components
--------------

EMG has a modular architecture, so one needs to know it to configure the plugin and/or even extend it properly. The picture below shows its components:

The input of the EMG component includes the configuration parameters (plugin configuration), specifications and the build base with the source code and its meta-information. 
The output of the component consists of several environment models for the given program fragment.

There are three main components in the EMG that a user must appropriately configure: Generator pipeline, Decomposer, and Translator. These components are considered below in detail, but we give information about their primary functions in this section.

The Generator pipeline runs several generators one by one. Generators yield parts of the IEM. Generated parts are independent and form the IEM as a parallel composition.

Decomposer separates the IEM into several simplified parts that can be verified independently. This step is optional.

Translator prepares the C code based on the provided IEM. It applies many simplifications to the input model. If there are several input models, several Translator instances are executed and generated FEMs are independent. 

.. figure:: ./media/env/emg-arch.png

EMG Configuration
-----------------

There are the following main configuration parameters of the EMG plugin:

**Parameter**: "specifications set"
**Value type**: String
**Default value**:
**Description**: The value is an identifier of the specification set.For example, an identifier can correspond to a particular Linux kernel version. The LinuxModule generator expects one of the following values: 3.14, 4.6.7, 4.14, 4.16, 5.5. The parameter can be provided directly in the job.json file.

.. list-table:: Frozen Delights!
    :widths: 10 25 10 55
    :header-rows: 1
    :align: left
    :class: tight-table  

    * - Configuration Parameter
      - Value Type
      - Defaul Value
      - Description
    * - specifications set
      - String
      - None
      - The value is an identifier of the specification set.For example, an identifier can
        correspond to a particular Linux kernel version. The LinuxModule generator expects 
        one of the following values: 3.14, 4.6.7, 4.14, 4.16, 5.5. The parameter can be provided directly in 
        the :file:`job.json` file.
    * - generators options
      - Object
      - None
      - The list defines the sequence of generators in the Generators pipeline. For example:
        .. code-block:: python

            "generators options": [
            {"linuxModule": {}},  {"linuxInsmod": {}},       
            {"genericManual": {}}
            ]
    * - translation options            
      - Object
      - None
      - An object with configuration parameters for Translator.
    * - single environment model per fragment
      - Bool
      - true
      - The false value activates Decomposer. It is described in a separate section as its extra configuration parameters. This parameter is required to be set in job.json directly.
    * - dump types
      - Bool
      - false
      - The property is intended for debugging. Generate a file “type collection.json” with the list of imported types.
    * - dump source code analysis
      - Bool
      - false
      - The property is intended for debugging. Generate files “vars.json”, “functions.json”, “macros.json”.

Intermediate Environment Model
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

EMG generates an IEM before translating it to the C language. The model is combined as a parallel composition from parts prepared by generators. The model also can be fully designed by hand and provided directly to the EMG using a specific generator (genericManual). We refer to such input files as *user-defined environment model specifications UDEMS*. Specifications for other generators include only templates or additional information to generate parts of IEMs.

IEMs and UDEMSes have the same notation. It is a JSON file. However, the structure of files containing these two kinds of models is slightly different. We consider the notation of only UDEMSes below because such specifications include IEMs.

Structure of UDEMS
------------------

A root is an object that maps *specification set identifiers* (related to configuration property “specifications set” mentioned above) to specifications itself. Specification sets are intended to separate models for different versions of a program. The specification contains IEMs meant for particular program fragments. The example below shows the organization of a file with a UDEMS:


.. code-block:: python

    {
        "5.5": [
            {
                "fragments": [
                "ext-modules/manual_model/unsafe.ko",
                "ext-modules/manual_model/safe.ko"
                ],
                "model": {...}
            }
       ]
    }

Program fragment identifiers are generated automatically by Klever at verification. One can get these names from attributes of plugin reports or verification results in the web interface. Also, the PFG component report contains the list of all generated program fragments.

The “model” value is an IEM provided to the EMG.

We do not give the precise theoretical semantics of the notation in the document. You can find them in the following papers [Z18]_, [N18]_, [ZN18]_. Instead, we describe the semantics intuitively by making analogies with program execution. We say about execution and running of processes, but even in the C code, IEM cannot be ever executed. It is intended only for analysis by software verification tools, so we say this just to avoid overcomplications.

Each IEM is a parallel composition of transition systems called *processes*. Each transition system can be considered as a thread executed by an operating system. The model contains *environment processes*.  Each transition system has a state and can do actions to change the state. The state is defined by values of labels. Intuitively labels can be considered as local variables on the stack of a process. 

A model consists of a main process, environment processes and function models. Both three are described with process descriptions, but semantically they are different. The main process is like a thread that acts from the very beginning of a combination of a program and environment model. It may trigger execution of a program or send signals to activate environment processes. While a program code is executed, it may call functions that are replaced by models. Function models are not processes or threads in any sense, they just act within the same scope, they can send signals to environment processes but cannot receive any. 

Environment processes exist from the very beginning of execution as the main process does. But any such process expects a signal to be sent to it for activation before doing any other activity. Signals are described below in more detail.

Each label has a C type. Any process can do block actions and send/receive signals. A block action is a C base block with C statements over program fragment global variables and labels. Signals pass values of labels and synchronize the sequence of actions between processes.

Process Actions
---------------

A process performs actions. There are actions of following kinds:

* block actions describe operations performed by the model.
* send/receive actions establish synchronization.
* jump actions help to implement loops and recursion.

The behavior of an environment model is often nondeterministic, Let’s consider a typical combination of an environment model with a program fragment source code. The semantics will be the following:

* The main process starts doing its actions from the very beginning first.
* It would either call a function from the program fragment or send an activating signal to any of environment model processes.
* The process transfer follows the rendezvous protocol:
* The sender waits until there is a receiver in the state when it can take a receiving action. 
  
  * Then the receive happens in no time. Nothing can happen during the receive.
  * If a receiver or a sender may do any other action instead of signal sending, they are allowed to attempt it leaving the other process still waiting. But if a process has the only option (sending or receiving a signal), then it cannot bypass it.
  * If there are several possible receivers or dispatchers, then the two are chosen randomly.




.. [Z18] I. Zakharov, E. Novikov. Compositional Environment Modelling for Verification of GNU C Programs. In Proceedings of the 2018 Ivannikov Ispras Open Conference (ISPRAS'18), pp. 39-44. IEEE Computer Society, 2018. https://doi.org/10.1109/ISPRAS.2018.00013.

.. [N18] E. Novikov, I. Zakharov. Verification of Operating System Monolithic Kernels Without Extensions. In: Margaria T., Steffen B. (eds) Proceedings of the 8th International Symposium on Leveraging Applications of Formal Methods, Verification, and Validation. Industrial Practice (ISoLA’18), LNCS, volume 11247, pp. 230–248. Springer, Cham. 2018. https://doi.org/10.1007/978-3-030-03427-6_19.

.. [ZN18] E. Novikov, I. Zakharov. Towards automated static verification of GNU C programs. In: Petrenko A., Voronkov A. (eds) Proceedings of the 11th International Andrei Ershov Memorial Conference on Perspectives of System Informatics (PSI’17), LNCS, volume 10742, pp. 402–416. Cham, Springer. 2018. https://doi.org/10.1007/978-3-319-74313-4_30.
