.. _dev_verifier_profiles:

Development of Verifier Profiles
================================

Verification tools have different capabilities.
Klever extensively uses CPAchecker as a verification backend, and it also has a variety of analyses implemented.
Klever primarily uses predicate analysis, value analysis, Symbolic Memory Graphs, and CPA Lockator techniques.
A user may need to know how to configure Klever to apply the best suiting configuration of a verification tool to cope with a particular program.
The choice would depend on a program complexity and safety property to check the program against.
Function pointers management, dynamic data structures, arrays, floating-point and bit-precise arithmetics, parallel execution are supported only by specific configurations.
Specific safety properties such as memory safety or the absence of data races can be checked only by particular analyses.
Klever provides a format to define configurations of specific safety properties that can be chosen or modified manually to adjust them for user needs.
Such configuration files are called *verification profiles* and this section gives a tutorial to them.

Verification profiles are described in a :file:`presets/jobs/verifier profiles.json` file in the :term:`$KLEVER_SRC` directory.
Below we consider its structure.

The first attribute of the file is *templates*. Each template has a comment (*description*), options set by *add options* and *architecture dependant options* and the ancestor defined by *inherit*.
Options are collected from the ancestor and then updated according to options described in *add options* and *architecture dependant options*.
Inheritance is possible only from another template.

Architecture can be set by the *architecture* attribute in the :file:`job.json` file.
It results in choosing the suitable additional options for verification tools provided within *architecture dependant options* entry.

There is an example below with three described options:

.. code-block:: json

  "add options": [
    {"-setprop": "cpa.callstack.unsupportedFunctions=__VERIFIER_nonexisting_dummy_function"},
    {"-setprop": "shutdown.timeout=100"},
    {"-heap": "%ldv:memory size:0.8:MB%m"}
  ]

Each entry is an object that has a single entry providing an option name and its value. Some options have empty strings as values.
The last option in the list has a specific format that allows Klever to adjust the amount of memory for the heap.
It equals to 80% of memory allocated for the verification tool in the example.

Requirement specifications require to provide certain profiles and verification tools versions.
These profiles are described in *profiles* member.
Let's consider an example of a *reachability* profile:

.. code-block:: json

  "profiles": {
    "reachability": {
      "CPAchecker": {
        "klever_fixes:38771": {"inherit": "CPAchecker BAM reachability"}
      },
      "UltimateAutomizer": {"v0.1.20": {"inherit": "Ultimate common"}}
    }
  }

The *reachability* profile can be used in requirement specifications.
The profile allows using two verification tools named CPAchecker and UltimateAutomizer.
Consult with the developer documentation or contact Klever's developers to learn how to support more verification tools.
The next objects in the example have verification tools' versions as keys and inheritance descriptions as values.
The latter says from which existing template the profile is inherited.
Note that it is possible to use different templates for distinguished versions of a verification tool in a single verification profile.
