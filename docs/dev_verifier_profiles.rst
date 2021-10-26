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
Such configuration files are called "verification profiles" and this section gives a tutorial to them.
