# Klever

Klever is a software verification framework designed to automate the checking
of industrial systems written in GNU C against a variety of requirements.
It employs software model checkers — automatic static verification tools
that apply advanced static analysis techniques such as Counterexample-Guided
Abstraction Refinement (CEGAR) [(Mandrykin, 2013)].

Software model checking [(Handbook, 2018)]
enables the detection of faults that are often difficult to uncover
with other quality assurance methods, including code review, testing, and
conventional static analysis. Moreover, it can formally prove the correctness of
programs with respect to specific requirements under certain assumptions.

[(Clarke, 2000)]: https://doi.org/10.1007/10722167_15 "CEGAR"
[(Mandrykin, 2013)]: https://ispranproceedings.elpub.ru/jour/article/view/959 "Introduction to CEGAR (in Russ.)"
[(Handbook, 2018)]: https://doi.org/10.1007/978-3-319-10575-8 "Handbook of Model Checking"

Klever currently supports verification of Linux kernel loadable modules,
Linux kernel subsystems and BusyBox applets. This can be further extended
by developing corresponding configurations, specifications and, perhaps,
adapting Klever components to specifics of target software.

Klever uses [our fork](https://gitlab.ispras.ru/verification/cpachecker)
of CPAchecker as its primary verification engine, but other tools from the
[Competition on Software Verification (SV-COMP)](https://sv-comp.sosy-lab.org/)
can also be used. Klever can detect:
- memory safety errors using Symbolic Memory Graphs (SMG)
[(Vasilyev, 2020)], [(Dudka, 2024)];
- data races using thread-modular analysis with projections
[(Andrianov, 2021)], [(Andrianov, 2020)];
- incorrect usage of the most popular Linux kernel API [(LDV, 2015)]
using predicate analysis [(CPAchecker, 2024)].

[(Vasilyev, 2020)]: https://doi.org/10.1134/S0361768820080071 "Predicate Extension of SMG"
[(Dudka, 2024)]: https://doi.org/10.48550/arXiv.2403.18491 "Predator Shape Analyzer"
[(Andrianov, 2021)]: https://doi.org/10.1007/978-3-030-72013-1_25 "CPALockator in SV-COMP"
[(Andrianov, 2020)]: https://doi.org/10.1007/978-3-030-57663-9_24 "Experiments on drivers"
[(LDV, 2015)]: https://doi.org/10.1134/S0361768815010065 "Toolset for OS Verification"
[(CPAchecker, 2024)]: https://doi.org/10.48550/arXiv.2409.02094 "CPAchecker 3.0: Tutorial (extended)"

Using formal specifications, Klever generates environment models that simulate
interrupts, timers, callbacks for various device types (USB, PCI, SCSI, NET,
etc.), file system operations, and other widely used interfaces. This approach
achieves over 50% code coverage for Linux device drivers and subsystems.
False alarm rates range from 0% to 80%, depending on the checked requirements.
Verification results can be incrementally improved by refining existing
specifications and adding new ones.

Klever includes a multi-user web interface to manage verification processes
and support expert assessment of results. The interface displays code coverage,
error traces, and statistics such as the number of detected bugs and false alarms.
An error trace contains all statements from the program entry point to the detected
error, supplemented with with possible values of variables and function arguments.
Most details are collapsed by default to keep traces comprehensible.
Experts can assign marks that are automatically associated with all similar error
traces, so the results can be compared across different runs.


## Found bugs
Klever has been used to find a several hundred acknowledged bugs in the Linux kernel:

- [commits since 2024][commits2024]
- [commits up to 2022][commits2022]
- [Linux Driver Verification list up to 2019](http://linuxtesting.org/results/ldv)
- [LDV list for CPAchecker](http://linuxtesting.org/results/ldv-cpachecker)

[commits2022]: https://git.kernel.org/pub/scm/linux/kernel/git/stable/linux.git/log/?qt=grep&q=Found+by+Linux+Driver+Verification+project+%28linuxtesting.org%29
[commits2024]: https://git.kernel.org/pub/scm/linux/kernel/git/torvalds/linux.git/log/?qt=grep&q=Found+by+Linux+Verification+Center+%28linuxtesting.org%29+with+Klever%29


## Publications
You can find more information about Klever in the following papers and presentations:

1. I.Zakharov, M.Mandrykin, V.Mutilin, E.Novikov, A.Petrenko, A.Khoroshilov, 2015.
Configurable toolset for static verification of operating systems kernel modules.
[(doi)][(LDV, 2015)]
1. E.Novikov, I.Zakharov, 2018.
Towards automated static verification of GNU C programs.
[(doi)](https://doi.org/10.1007/978-3-319-74313-4_30)
[(forge)](https://forge.ispras.ru/documents/73)
1. E.Novikov, I.Zakharov, 2018.
Verification of Operating System Monolithic Kernels Without Extensions.
[(doi)](https://doi.org/10.1007/978-3-030-03427-6_19)
[(forge)](https://forge.ispras.ru/documents/74)
1. E.Novikov, 2019. Klever: Enabling Model Checking for the Linux Kernel.
[(forge)](https://forge.ispras.ru/documents/75)
1. I.Zakharov, E.Novikov, I.Shchepetkov, 2023.
Klever: Verification Framework for Critical Industrial C Programs.
[(doi)](https://doi.org/10.48550/arXiv.2309.16427)


## Additional resources
Klever read-only mirrors:
- <https://github.com/ldv-klever/klever>.
- <https://forge.ispras.ru/projects/klever>

If you have any questions, feel free to email <ldv-project@linuxtesting.org>.


## Klever Documentation

The Klever documentation provides detailed
[deployment instructions](https://klever.readthedocs.io/en/latest/deploy.html),
a tutorial with basic workflow, manuals for various use cases and some instructions
for developers. You can find it online at <http://klever.readthedocs.io>
or build it yourself.

To build the Klever documentation you need:
* Install [Python 3.4 or higher](https://www.python.org/).
* Install [Sphinx](http://sphinx-doc.org) and its
  [Read the Docs theme](https://sphinx-rtd-theme.readthedocs.io/en/latest/), e.g.:

      pip3 install sphinx sphinx_rtd_theme

  or in a more reliable way:

      pip3 install -r docs/requirements.txt

* Execute the following command from the source tree root directory (it should be executed each time when the
  documentation might be changed):

      make -C docs html

Then you can open generated documentation index "docs/_build/html/index.html" in a web browser.
