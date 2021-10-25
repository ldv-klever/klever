.. _dev_decomposition_conf:

Development of Program Decomposition Specifications
===================================================

The section presents a tutorial for program decomposition in Klever.
Thorough verification is poorly scalable.
Thus, one needs to bound the scope of each verification goal.
Decomposition of a program into :term:`program fragments <Program fragment>` is an essential solution for reducing verification complexity.
The decomposition process should be done very accurately to balance required efforts for environment modeling and verification tool capabilities.
It is hardly possible to propose any fully automatic solution to this problem.
Klever provides means for both manual and automatic selection of files into fragments to meet user needs.
