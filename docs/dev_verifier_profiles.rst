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

.. _dev_verifier_profiles:

Development of Verifier Profiles
================================

Verification tools have different capabilities.
Klever extensively uses `CPAchecker <https://cpachecker.sosy-lab.org/>`__ as a verification backend.
CPAchecker has a variety of analyses implemented.
Klever primarily uses predicate analysis, value analysis, symbolic memory graphs and finding data races.
A user may need to know how to configure Klever to apply the best suiting configuration of a verification tool to cope
with a particular program.
The choice would depend on a program complexity and safety property to check the program against.
Function pointers management, dynamic data structures, arrays, floating-point and bit-precise arithmetics, parallel
execution are supported only by specific configurations.
Specific safety properties such as memory safety or the absence of data races can be checked only by particular
analyses.
Klever provides a format to define configurations of specific safety properties that can be chosen or modified manually
to adjust them for user needs.
Such configuration files are called *verification profiles* and this section gives a tutorial on them.

Verification profiles are described in the :file:`presets/jobs/verifier profiles.json` file in the :term:`$KLEVER_SRC`
directory.
Below we consider its structure.
The first attribute of the file is *templates*.
Each template can have:

* A comment (*description*).
* Options set by *add options* and *architecture dependant options*
* The ancestor defined by *inherit*.

Options are collected from the ancestor and then updated according to options described in *add options* and
*architecture dependant options*.
Inheritance is possible only from another template.

Architecture can be set by the *architecture* attribute in the :file:`job.json` file.
It results in choosing the suitable additional options for verification tools provided within
*architecture dependant options* entry.

There is an example below with three described options:

.. code-block:: json

  "add options": [
    {"-setprop": "cpa.callstack.unsupportedFunctions=__VERIFIER_nonexisting_dummy_function"},
    {"-ldv-bam": ""}
    {"-heap": "%ldv:memory size:0.8:MB%m"}
  ]

Each entry is an object that has a single entry providing an option name and its value.
Some options have empty strings as values.
The last option in the list has a specific format that allows Klever to adjust the amount of memory for the heap.
It equals to 80% of memory allocated for the verification tool in the example.
You can find a complete list of CPAchecker's options
`here <https://gitlab.com/sosy-lab/software/cpachecker/-/blob/trunk/doc/ConfigurationOptions.txt>`__.

Requirement specifications should be provided with certain verification profiles and verification tools versions.
They are described in the *profiles* attribute.
Let's consider an example of a *reachability* verification profile:

.. code-block:: json

  "profiles": {
    "reachability": {
      "CPAchecker": {"klever_fixes:38771": {"inherit": "CPAchecker BAM reachability"}},
      "UltimateAutomizer": {"v0.1.20": {"inherit": "Ultimate common"}}
    }
  }

The *reachability* profile can be used at description of requirement specifications within appropriate requirement
specification bases.
The verification profile allows using two verification tools named CPAchecker and UltimateAutomizer.
The next objects in the example have verification tools' versions as keys and inheritance descriptions as values.
The latter refers the template that is inherited by the verification profile.
Note that it is possible to use different templates for distinguished versions of a verification tool in a single
verification profile.

You need to refer the developer documentation or contact Klever's developers to learn how to support more verification
tools as well as additional configuration options for supported verification tools.
