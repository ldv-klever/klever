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

.. _dev_req_specs:

Development of Requirement Specifications
=========================================

To check requirements with Klever it is necessary to develop *requirement specifications*.
This part of the user documentation describes how to do that.
It will help to fix both existing requirement specifications and to develop new ones.
At the moment this section touches just rules of correct usage of specific APIs while some things may be the same for
other requirements.

In ideal development of any requirements specification should include the following steps:

#. Analysis and description of checked requirements.
#. Development of the requirements specification itself.
#. Testing of the requirements specification.

If you will meet some issues on any step, you should repeat the process partially or completely to eliminate them.
Following subsections consider these steps in detail.
As an example we consider a requirements specification devoted to correct usage of a module reference counter API in the
Linux kernel.

Analysis and Description of Checked Requirements
------------------------------------------------

At this step one should clearly determine requirements to be checked.
For instance, for rules of correct usage of specific APIs it is necessary to describe related elements of APIs and
situations when APIs are used wrongly.
Perhaps, various versions and configurations of target programs can provide APIs differently while considered
correctness rules may be the same or almost the same.
If you would like to support these versions/configurations, you should also describe corresponding differences of APIs.

There are different sources that can help you to formulate requirements and to study APIs.
For instance, for the Linux kernel they are as follows:

* Documentation delivered together with the source code the Linux kernel (directory :file:`Documentation`) as well as
  the source code of the Linux kernel itself.
* Books, papers and blog posts devoted to development of the Linux kernel and its loadable modules such as device
  drivers.
* Mailing lists, including `Linux Kernel Mailing List <https://lkml.org/>`__.
* The history of development in Git.

Using the latter source you can find out bugs fixed in target programs.
These bugs can correspond to common weaknesses of C programs like buffer overflows as well as they can implicitly refer
to specific requirements, in particular rules of correct usage of specific APIs.

Technically it is possible to check very different requirements within the same specification, but we do not recommend
to do this due to some limitations of software model checkers (*verification tools*).
Nevertheless, you can formulate and check requirements related to close API elements together.

Let's consider rules of correct usage of the module reference counter API in the Linux kernel.
For brevity we will not consider some elements of this API.

Linux loadable kernel modules can be unloaded just when there is no more processes using them.
One should call :c:func:`try_module_get()` in order to notify the Linux kernel that module is still in use.

.. c:function:: bool try_module_get(struct module *module)

    Try to increment the module reference count.

    :param module: The pointer to the target module. Often this the given module.
    :return: *True* in case when the module reference counter was increased successfully and *False* otherwise.

To give the module back one should call :c:func:`module_put()`.

.. c:function:: void module_put(struct module *module)

    Decrement the module reference count.

    :param module: The pointer to the target module.

There are static inline stubs of these functions when module unloading is disabled via a special configuration of the
Linux kernel (**CONFIG_MODULE_UNLOAD** is unset).
One can consider them as well, though, strictly speaking, in this case there is no requirements for their usage.

Correctness rules can be formulated as follows:

#. One should not decrement non-incremented module reference counters. Otherwise the kernel can unload modules in use
   that can result to different issues.
#. Module reference counters should be decremented to their initial values before finishing operation. If this will not
   be the case one will not be able to unload modules ever.

Development of Requirements Specification
-----------------------------------------

Development of each requirements specification includes the following steps:

#. Developing a model of an API.
#. Binding the model with original API elements.
#. Description of the new requirements specification.

.. TODO: the paragraph below is common for development of all specifications and configurations in Klever.

We recommend to develop new requirement specifications on the basis of existing ones to avoid various tricky issues and
to speed up the whole process considerably.
Also, we recommend you to deploy Klever in the *development* mode (:ref:`local_deploy`).
In this case you will get much more debug information that can help you to identify various issues.
Moreover, you will not even need to update your Klever installation.
Though Web UI supports rich means for creating, editing and other operations with verification job files including
specifications, we recommend you to develop requirement specifications directly within :term:`$KLEVER_SRC` by means of
some IDE or editor.
To further reduce manual efforts using such the workflow, you can temporarily modify necessary preset verification jobs,
e.g. to specify requirement specifications and program fragments of interest within :file:`job.json`.
Do not forget to not commit these temporary changes to the repository!

Developing Model
^^^^^^^^^^^^^^^^

First of all you should develop a model of a considered API and specify pre- and postconditions of API usage within that
model.
Klever suggests to use the C programming language for this purpose while one can use some library functions having a
special semantics for software model checkers, e.g. for modeling nondeterministic behavior, for using sets and maps,
etc.

The model includes a *model state* that is represented as a set of global variables usually.
Besides, it includes *model functions* that change the model state and check for pre- and postconditions according to
semantics of the modelled API.

Ideally the model behavior should correspond to behavior of the corresponding implementation.
However in practice it is rather difficult to achieve this due to complexity of the implementation and restrictions of
verification tools.
You can extend the implementation behavior in the model.
For example, if a function can return one of several error codes in the form of the corresponding negative integers,
the model can return any non-positive number in case of errors.
It is not recommended to narrow down the implementation behavior in the model (e.g. always return 0 though the
implementation can return values other than 0) as it can result in some paths will not be considered and the overall
verification quality will decrease.

In the example below there is the model state represented by global variable **ldv_module_refcounter** initialized by 0.
This variable is changed within model functions **ldv_try_module_get()** and **ldv_module_put()** according to the
semantics of the corresponding API.

The model makes 2 checks by means of **ldv_assert()**.
The first one is within **ldv_module_put()**.
It is intended to find out cases when modules decrement the reference counter without incrementing it first.
The second check is within **ldv_check_final_state()** invoked by the :term:`environment model <Environment model>`
after modules are unloaded.
It tracks whether modules decrement reference counters to their initial values before finishing their operation.

.. code-block:: c

    /* Definition of struct module. */
    #include <linux/module.h>
    /* Definition of ldv_assert() that calls __VERIFIER_error() when its argument is not true. */
    #include <ldv/verifier/common.h>
    /* Definition of ldv_undef_int() invoking __VERIFIER_nondet_int(). */
    #include <ldv/verifier/nondet.h>

    /* NOTE Initialize module reference counter at the beginning */
    static int ldv_module_refcounter = 0;

    int ldv_try_module_get(struct module *module)
    {
        /* NOTE Nondeterministically increment module reference counter */
        if (ldv_undef_int()) {
            /* NOTE Increment module reference counter */
            ldv_module_refcounter++;
            /* NOTE Successfully incremented module reference counter */
            return 1;
        }
        else
            /* NOTE Could not increment module reference counter */
            return 0;
    }

    void ldv_module_put(struct module *module)
    {
        if (ldv_module_refcounter < 1)
            /* ASSERT One should not decrement non-incremented module reference counters */
            ldv_assert();

        /* NOTE Decrement module reference counter */
        ldv_module_refcounter--;
    }

    void ldv_check_final_state(void)
    {
        if (ldv_module_refcounter)
            /* ASSERT Module reference counter should be decremented to its initial value before finishing operation */
            ldv_assert();
    }

It is worth noting that model functions do not refer their parameter **module**, i.e. they consider all modules the
same.
This can result to both false alarms and missed bugs.
Nevertheless, often it does have sense to do such tricks to avoid too complicated models for verification, e.g. accurate
tracking of dynamically created objects of interest using lists.
Another important thing is modelling of nondeterminism in **ldv_try_module_get()** by invoking **ldv_undef_int()**.
Thanks to it a software model checker will cover paths when **try_module_get()** can successfully increment the module
reference counter and when this is not the case.

In the example above you can see comments starting with words **NOTE** and **ASSERT**.
These comments are so called *model comments*.
They emphasize expressions and statements that make some important actions, e.g. changing the model state.
Later these comments will be used during visualization and expert assessment of verification results.
You should place model comments just before corresponding expressions and statements.
Each model comment has to occupy the only line.

The given API model is placed into a separate C file that will be considered alongside the source code of verified
modules.
A bit later we will discuss how to name this file and where to place it.

Binding Model with Original API Elements
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

To activate the API model you should bind model functions to points of use of original API elements.
For this purpose we use an aspect-oriented extension for the C programming language.
Below there is a content of an aspect file for the considered example.
It replaces calls to functions :c:func:`try_module_get()` and :c:func:`module_put()` with calls to corresponding model
functions **ldv_try_module_get()** and **ldv_module_put()**.

.. code-block:: c

    before: file ("$this") {
    /* Definition of struct module. */
    #include <linux/module.h>

    extern int ldv_try_module_get(struct module *module);
    extern void ldv_module_put(struct module *module);
    }

    around: call(bool try_module_get(struct module *module))
    {
        return ldv_try_module_get(module);
    }

    around: call(void module_put(struct module *module))
    {
        ldv_module_put(module);
    }

It is not hard to accomplish this aspect file with bindings for static inline stubs of these functions.

The aspect file above contains declarations of model functions.
You can place them into a separate header file and include that file into both the C file and the aspect file.

If you will need to keep original function calls, you can use either before/after advices or include those calls
directly in advices themselves like in the examples below:

.. code-block:: c

    /* Original function will be invoked after ldv_func_pre() and its return value will be returned eventually. */
    before: call(int func(int arg))
    {
        ldv_func_pre(arg);
    }

.. code-block:: c

    /* Original function will be invoked before ldv_func_post() and its return value will be returned eventually.
       Besides, it is available as $res in advice body. */
    after: call(int func(int arg))
    {
        ldv_func_post(arg, $res);
    }

.. code-block:: c

    around: call(int func(int arg))
    {
        int ret;
        ldv_func_pre(arg);
        ret = func(arg);
        ldv_func_post(arg, ret);
        return ret;
    }

Unless you are using options "weave in model aspect" and "weave in all aspects", you can invoke original functions
within model functions.
Otherwise, you will have recursion due to those original function calls will be also woven in.

Description of New Requirements Specification
^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^

Bases of requirement specifications are located in JSON files corresponding to projects, e.g. :file:`Linux.json`, within
directory :term:`$KLEVER_SRC`:file:`/presets/jobs/specifications`.
Also, there is corresponding directory :file:`specifications` in all verification jobs.
Each requirements specification can contain one or more C source files with API models.
We suggest to place these files according to the hierarchy of files and directories with implementation of the
corresponding API elements.
For example, you can place the C source file from the example above into
:term:`$KLEVER_SRC`:file:`/presets/jobs/specifications/linux/kernel/module.c` as the module reference counter API is
implemented in file :file:`kernel/module.c` of the Linux kernel.

Additional files such as aspect files should be placed in the same way as C source files but using appropriate
extensions, e.g. :term:`$KLEVER_SRC`:file:`/presets/jobs/specifications/linux/kernel/module.aspect`.
You should not specify aspect files within the base since they are found automatically.

As a rule identifiers of requirement specifications are chosen according to relative paths of C source files with main
API models.
For example, for the considered example it is **kernel:module**.
Requirement specification bases represent these identifiers in the tree form.

Testing of Requirements Specification
-------------------------------------

We recommended to carry out different types of testing to check syntactic and semantic correctness of requirement
specifications during their development and maintenance:

#. Developing a set of rather simple test programs, e.g. external Linux loadable kernel modules, using the modelled API
   incorrectly and correctly.
   The verification tool should report Unsafes and Safes respectively unless you will develop such the test programs
   that do not fit your models.
#. Validating whether known violations of checked requirements can be found.
   Ideally the verification tool should detect violations before their fixes and it should not report them after that.
   In practice, the verification tool can find other bugs or report false alarms, e.g. due to inaccurate environment
   models.
#. Checking target programs against requirement specifications.
   For example, you can check all loadable kernel modules of one or several versions or configurations of the Linux
   kernel or consider some relevant subset of them, e.g. USB device drivers when developing appropriate requirement
   specifications.
   In ideal, a few false alarms should be caused by incorrectness or incompleteness of requirement specifications.

For item 1 you should consider existing test cases and their descriptions in the following places:

* :term:`$KLEVER_SRC`:file:`/klever/cli/descs/linux/testing/requirement specifications/tests/linux/kernel/module`
* :term:`$KLEVER_SRC`:file:`/klever/cli/descs/linux/testing/requirement specifications/desc.json`
* :term:`$KLEVER_SRC`:file:`/presets/jobs/linux/testing/requirement specifications`

For item 2 you should consider existing test cases and their descriptions in the following places:

* :term:`$KLEVER_SRC`:file:`klever/cli/descs/linux/validation/2014 stable branch bugs/desc.json`
* :term:`$KLEVER_SRC`:file:`presets/jobs/linux/validation/2014 stable branch bugs`

In addition, you should refer :ref:`test_build_bases_generation` to obtain build bases necessary for testing and
validation.

Requirement specifications can be incorrect and/or incomplete.
In this case test and validation results will not correspond to expected ones.
It is necessary to fix and improve the requirements specification while you will have appropriate resources.
Also, you should take into account that non-ideal results can be caused by other factors, for example:

* Incorrectness and/or incompleteness of :term:`environment models <Environment model>`.
* Inaccurate algorithms of the verification tool.
* Generic restrictions of approaches to development of requirement specifications, e.g. when using counters rather than
  accurate representations of objects.

Using Argument Signatures to Distinguish Objects
------------------------------------------------

As it was specified above, it may be too hard for the verification tool to accurately distinguish different objects like
modules and mutexes since this can involve complicated data structures.
From the other side treating all objects the same, e.g. by using integer counters when modeling operations on them, can
result in a large number of false alarms as well as missed bugs.
For instance, if a Linux loadable kernel module acquires two different mutexes sequentially, the verification tool will
detect that the same mutex can be acquired twice that will be reported as an error.

To distinguish objects we suggest using so-called *argument signatures* — identifiers of objects which are calculated
syntactically on the basis of the expressions passed as corresponding actual parameters.
Generally speaking different objects can have identical argument signatures.
Thus, it is impossible to distinguish them in this way.
Ditto the same object can have different argument signatures, e.g. when using aliases.
Nevertheless, our observation shows that in most cases the offered approach allows to distinguish objects rather
precisely.

Requirement specifications with argument signatures differ from requirement specifications which were considered
earlier.
You need to specify different model variables, model functions and preconditions for each calculated argument signature.
For the example considered above it is necessary to replace:

.. code-block:: c

    /* NOTE Initialize module reference counter at the beginning */
    static int ldv_module_refcounter = 1;

    int ldv_try_module_get(struct module *module)
    {
        /* NOTE Nondeterministically increment module reference counter */
        if (ldv_undef_int() == 1) {
            /* NOTE Increment module reference counter */
            ldv_module_refcounter++;
            /* NOTE Successfully incremented module reference counter */
            return 1;
        }
        else
            /* NOTE Could not increment module reference counter */
            return 0;
    }

with:

.. code-block:: c

    // for arg_sign in arg_signs
    /* NOTE Initialize module reference counter{{ arg_sign.text }} at the beginning */
    static int ldv_module_refcounter{{ arg_sign.id }} = 1;

    int ldv_try_module_get{{ arg_sign.id }}(struct module *module)
    {
        /* NOTE Nondeterministically increment module reference counter{{ arg_sign.text }} */
        if (ldv_undef_int() == 1) {
            /* NOTE Increment module reference counter{{ arg_sign.text }} */
            ldv_module_refcounter{{ arg_sign.id }}++;
            /* NOTE Successfully incremented module reference counter{{ arg_sign.text }} */
            return 1;
        }
        else
            /* NOTE Could not increment module reference counter{{ arg_sign.text }} */
            return 0;
    }
    // endfor

In bindings of model functions with original API elements it is necessary to specify for what function arguments it i
necessary to calculate argument signatures.
For instance, it is necessary to replace:

.. code-block:: c

    around: call(bool try_module_get(struct module *module))
    {
        return ldv_try_module_get(module);
    }

with:

.. code-block:: c

    around: call(bool try_module_get(struct module *module))
    {
        return ldv_try_module_get_$arg_sign1(module);
    }

Models and bindings that use argument signatures should be described differently within requirement specification bases.
It is recommended to study how to do this on the base of existing examples, say, **kernel:locking:mutex**.

You can find more details about the considered approach in [N13]_.

.. [N13] Novikov E.M. Building Programming Interface Specifications in the Open System of Componentwise Verification of
         the Linux Kernel. Proceedings of the Institute for System Programming of the RAS (Proceedings of ISP RAS),
         volume 24, pp. 293-316. 2013. https://doi.org/10.15514/ISPRAS-2013-24-13. (In Russian)
