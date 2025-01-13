# Klever 4.0 (2025-01-13)

This is a release of the framework that focuses on performance issues and integration with continuous verification.

The following fixes and improvements in Klever 4.0 deserve an attention:
* Large refactoring in Klever Core, including:
   * Replace data transfer from files to memory data structures
   * Disable useless reports
   * Remove confusing callbacks
   * Remove extra processes
   * Remove extra multiprocessing queues and components
   * Remove tasks upload to Bridge in case of local deploy
   * Add an option to disable cross references
   * Optimize main job page in web interface
   * Remove legacy code
* New versions of verifiers, based on CPAchecker 3.1
* Different improvements in resources, particularly, memory limits for main process, thread pool, node resources, speculative scheduling, EMG.
* Minor fixes in EMG models
* Scripts for build base creation.
* Development is moved into gitlab repository

We would like to thank very much everybody who made this great job possible!

# Klever 3.7 (2022-08-26)

Following fixes and improvements in Klever 3.7 deserve an attention:

* Adding new environment models for the Linux kernel:
  * Modeling the *list* API.
  * Modeling the *kref* API.
  * Adding model for the *input_ff_create_memless()* function.
  * Adding models for *check_add_overflow()*, *check_sub_overflow()* and *check_mul_overflow()* macros that fixes the *struct_size()* model for new versions of the Linux kernel.
  * Modeling *v4l2_device_(un)register()* functions.
  * Modeling the *i2c_match_id()* function.
  * Adding model for the *dev_err_probe()* function.
  * Adding models for the dynamic debug printing API.
* Fixing existing environment models for the Linux kernel:
  * Modeling failures for *calloc()* and *zalloc()*.
  * Fixing the off-by-one error when choosing a device from *MODULE_DEVICE_TABLE*.
  * Passing the same resource to probe and remove for HID drivers.
  * Allocating memory for *inode* for *file_operations* callbacks.
  * Allocating memory for *tty_struct* for *tty_operations* callbacks.
  * Avoiding using implicit resources in environment model specifications.
* Adding a new section to the user documentation: [Verifying New Program](https://klever.readthedocs.io/en/latest/verifying_new_program.html).
* Fixing tests for environment model specifications and Environment Model Generator.
* Updating CIF which main file was rewritten in C++ and that started to print keyword *static* for local variables.
* Updating CPAchecker that supports packed/aligned attributes and issues violation witnesses more efficiently.
* Updating Python dependencies.

# Klever 3.6 (2022-06-26)

Klever 3.6 was released pretty soon after Klever 3.5 since we updated Clade and CIF in the backward incompatible manner.
This means that the new version of Klever requires all build bases to be regenerated with the new version of Clade and CIF installed together with Klever.
You can download build bases for Linux 5.5.19, 5.10.120 and 5.17.13 as well as sample build bases prepared ahead of time.
The [Klever tutorial](https://klever.readthedocs.io/en/v3.6/tutorial.html#preparing-build-bases) provides corresponding links.

Other changes in Klever 3.6 are new models for *struct_size()* and underlying *__ab_c_size()* for the Linux kernel.

# Klever 3.5 (2022-05-27)

We released Klever 3.5 that has following noticeable changes:

* Improving support for verification of Linux 5.10 and Linux 5.17 (new specifications set "5.17" was added).
* Environment models generated at verification of Linux loadable kernel modules do not contain infinite loops anymore.
  This accelerated analysis and did not result in any degradation in the quality of verification results.
* Using [Ubuntu 20.04](https://wiki.ubuntu.com/FocalFossa/ReleaseNotes), [Debian 11](https://wiki.ubuntu.com/FocalFossa/ReleaseNotes) and [openSUSE 15](https://wiki.ubuntu.com/FocalFossa/ReleaseNotes).3 as preferable Linux distributions for deployment of Klever.
* Switching to Python 3.10.
  You should carefully read this [comment](https://forge.ispras.ru/issues/10937#note-7) if you are going to update existing local instances of Klever.
* Supporting regular expressions for assessing unsafes.
* Updating [Klever Tutorial](https://klever.readthedocs.io/en/v3.5/tutorial.html), in particular using verification of loadable kernel modules of Linux 5.5 as an example.
* Updating add-ons and verification back-ends (various bug fixes and optimizations).
* More advanced authorization of new users.
  Now the administrator should activate new users while somebody should grant them access to some jobs.

# Klever 3.4 (2022-02-24)

Klever 3.4 includes the following prominent features:

* Several improvements contributing development and generation of environment models:
  * Ability to specify savepoints for the main process.
  * Ability to select scenarios for particular savepoints manually.
  * Ability to configure the number of iterations for invocation of callbacks.
  * Providing users with a graphical representation of environment models directly in the Klever web UI.
* Models for *kmem_cache* functions for the Linux kernel.
* Updating add-ons and verification back-ends (various bug fixes and optimizations).
* New sections in the user documentation: [Configuring Program Decomposition](https://klever.readthedocs.io/en/latest/dev_decomposition_conf.html) and [Development of Verifier Profiles](https://klever.readthedocs.io/en/latest/dev_verifier_profiles.html).
* Besides, you can find the [CIF’s user documentation](https://cif.readthedocs.io/en/latest/index.html) that may be helpful at development of advanced specifications and models.
* Many fixes and minor improvements that make the specification development and verification workflow more easy, correct and reliable.

# Klever 3.3 (2021-10-20)

The most noticeable work in Klever 3.3 is a new section [Development of Environment Model Specifications](https://klever.readthedocs.io/en/latest/dev_env_model_specs.html) in the user documentation. Besides, there are following considerable improvements:

* Fixing allocation of memory for arguments of callbacks of several vital Linux device driver types.
* Enhancing environment model specifications for file systems.
* Simplifying development of environment model specifications and fixing some bugs at their processing
* Numerous enhancements of the Klever web UI that simplify several common use cases.
* Updating dependencies and addons that make them more functional and robust.
* Development of unit tests for deployment of Klever within the OpenStack cloud
* Supporting deployment at openSUSE.
* New section [Development of Common API Models](https://klever.readthedocs.io/en/latest/dev_common_api_models.html) in the user documentation.

# Klever 3.2 (2021-08-05)

The major improvement of Klever 3.2 is a new environment model generator that supports automated splitting of complex environment models into sets of smaller ones.
This is extremely helpful at verification of large programs and program fragments when verification tools often can not provide definite answers within specified time limits.

Other important changes are as follows:

* Substantially fixed and enhanced representation of violation witnesses (error traces) and code coverage reports as well as navigation through them.
* New environment models for the Linux kernel (the bitmap API and several functions working with strings).
* New validation set on the base of faults found by Klever and fixed in the Linux kernel.
* Supporting more reliable and efficient deployment of Klever within the OpenStack cloud.
* New section [Analysis of Code Coverage Reports](https://klever.readthedocs.io/en/latest/tutorial.html#analysis-of-code-coverage-reports) in the Klever tutorial.

# Klever 3.1 (2021-03-31)

The new release has the following major changes:

* Improved support for the ARM/ARM64 architecture.
* New parts within the user documentation:
  * [Klever CLI](https://klever.readthedocs.io/en/latest/dev_req_specs.html).
  * [Development of Requirement Specifications](https://klever.readthedocs.io/en/latest/dev_req_specs.html).
* Fixing existing models and specifications and development of the new ones:
  * Support deregistration of *pm_ops *callbacks.
  * Fixing models for *vmalloc()/vfree()* and friends.
  * Developing the model for *current*.
* Adding the ability to weave in models.
* Allowing excluding common models.
* Suggesting working source trees automatically (most likely you will not need to specify them manually for new build bases).
* Showing Klever version in Bridge.
* Updating vital Klever addons and dependencies:
  * [Clade 3.4](https://forge.ispras.ru/projects/astraver/repository/framac/revisions/18d3be82).
  * [CIF 746d8be](https://forge.ispras.ru/projects/cif/repository/110/revisions/746d8be0).
  * [Frama-C 18d3be8](https://forge.ispras.ru/projects/astraver/repository/framac/revisions/18d3be82) (switching from 18.0 to 20.0).
  * [CPAchecker klever_fixes:36955](https://github.com/sosy-lab/cpachecker/commit/4715b56).
  * [CPALockator CPALockator-combat-mode:36901](https://github.com/sosy-lab/cpachecker/commit/3491764).
* Support for the [new OpenStack cloud at ISP RAS](https://sky.ispras.ru/).


# Klever 3.0 (2021-01-11)

Among a lot of improvements and bug fixes, most significant changes in Klever 3.0 are as follows:

* Support for verification of kernel loadable modules of Linux 5.5.
* Support for verification of Linux kernel loadable modules on the ARM architecture.
* Fixing and developing specifications for verification of Linux kernel loadable modules:
  * Fixing specifications for checking usage of clocks in drivers.
  * Support for checking usage of the RCU API.
  * Developing detailed specifications for USB serial drivers.
  * Improving environment models for runtime power management callbacks.
  * Using device identifiers from the driver tables.
  * Developing models for *devm* memory allocating functions.
  * Fixing *framebuffer_alloc/release* models.
  * Adding models for *request/release_firmware()*, *v4l2_i2c_subdev_init()* and *i2c_smbus_read_block_data()*.
* More user-friendly configuration for target program fragments and requirement specifications.
* Development of preset tags for assessing most common false alarms.
* Support for new internal data formats for enhancing and optimizing representation and assessment of verification results.
* Support for cross-references for original program source files and models.
* Update of all variants of the [CPAchecker](https://cpachecker.sosy-lab.org/) verification back-end.
* Switching to a special version of Frama-C developed within project [Deductive Verification Tools for Linux Kernel](https://forge.ispras.ru/projects/astraver) from outdated and unmaintained CIL.
  Both tools are used for merging source files and optimizations like removing unused functions.
* Using systemd scripts instead of init.d ones for Klever services.
* Development of [Tutorial](https://klever.readthedocs.io/en/latest/tutorial.html).


# Klever 2.0 (2018-11-10)

Klever 2.0 implements ideas suggested in [[1](https://link.springer.com/chapter/10.1007/978-3-319-74313-4_30)].
In general we added support for verification of software written in the GNU C programming language.
First examples of using Klever for software that differs from Linux device drivers are verification of Linux kernel subsystems [[2](https://link.springer.com/chapter/10.1007/978-3-030-03427-6_19)] and [BusyBox](https://forge.ispras.ru/projects/clade) applets.
We are looking forward for more success stories!

Most important changes in Klever 2.0 are the following:

* Klever does not build programs under verification anymore.
  Instead it takes as input *build bases* that should be prepared with [Clade](https://forge.ispras.ru/projects/clade) in advance.
  This considerably speed ups verification when verifying the same software within different verification jobs.
  Also, this provides a more natural way to integrate Klever within a standard development life cycle.
* The generator of *program fragments* (former *verification objects*) includes abstract means suitable for various software as well as means for particular kinds of programs that allow to avoid considerable efforts for configuring program decomposition.
* The environment models generator consists of a number sub-generators that take specifications in suitable specific formats.
  This allows to simplify development of such the specifications very much.
  Besides, we fixed many existing and developed new environment model specifications both for new kinds of interactions between Linux kernel and BusyBox components and for new versions of the Linux kernel.
* The Klever interface provides users with a extremely useful online editor that enables changing configuration and specification files directly within the interface.

# Klever 1.1 (2018-09-05)

Klever 1.1 includes quite many high demanded features and fixes of the most annoying bugs:

* Improving coverage calculation and visualization.
  Now one can easily navigate through covered and uncovered functions.
* Updating CPALockator used for finding data races.
* Proper processing of wall timeouts that is especially important for highly overloaded machines.
* Advanced verification tasks scheduling allows:
  * Solving verification tasks faster by means of adaptation of computational resource limits.
  * Solving more verification tasks when having free computational resources after ensuring a minimally required quality of service.
* Getting rid of some database caches helps to avoid unpleasant bugs in various statistics.
* Considerable fixing and improving local and OpenStack deployments.
* Numerous minor bug fixes, optimizations and improvements.

# Klever 1.0 (2018-07-04)

This major version is dedicated to verification of Linux loadable kernel modules.

Klever 1.0 includes all issues scheduled for 0.3 since they take much more time than we expected (we did not release 0.3 at all).
Besides, there are many other fixes and improvements.
We would like to mention the most valuable ones:

* Verification results processing, visualization and assessment:
  * More accurate calculation and more pretty visualization of a verification job decision progress.
  * Adding more means for unknown report marks.
  * Improving error traces representation.
* Updating the [CPAchecker](https://cpachecker.sosy-lab.org/) verification back-end.
* Deployment:
  * Developing scripts for local deployment of Klever at Debian 9.
  * Improving deployment within OpenStack clouds.
  * Creating documentation that describes Klever deployment.
* Support of a command-line interface for Klever Bridge.
* Continuous integration:
  * Considerable enhancement of Klever tests.
  * Evaluating testing and validation results with preset marks.
  * Automated regression testing with help of Jenkins.
* Numerous improvements, optimizations and bug fixes that substantially contribute reliability, increase performance and facilitate manual operations.
  Too many issues to treat them individually.

# Klever 0.2 (2017-10-19)

Among all new features and bug fixes the most notable ones are the following:

* Verification results processing, visualization and assessment:
  * Improving calculation and visualization of code coverage for particular verification tasks.
  * Calculation and visualization of code coverage split by correctness rule specifications for verification jobs or sub-jobs as a whole.
  * Switching to new functions for converting and comparing error traces by default as well as removing the outdated ones.
  * Fixes of processing, visualization and comparison of error traces for data races.
* Verification back-ends:
  * Support for configuring verification back-ends.
  * Updating verification back-ends used by default.
  * Integration of [Ultimate Automizer](https://monteverdi.informatik.uni-freiburg.de/tomcat/Website/?ui=tool&tool=automizer) as an alternative verification back-end.
* Verification tasks generation:
  * Ability to generate verification tasks consisting of several C source files.
  * Parallel generation of verification tasks and processing of verification results.
  * Reusing intermediate results obtained during verification tasks generation.
* Support for installation and updates within OpenStack clouds.


# Klever 0.1 (2017-09-07)

Klever 0.1 includes extremely many awesome features to mention all of them explicitly.
