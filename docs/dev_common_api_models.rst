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

.. _dev_common_api_models:

Development of Common API Models
================================

Klever verifies :term:`program fragments <Program fragment>` rather than complete programs as a rule.
Moreover, target programs can invoke library functions that are out of scope at verification.
This can result in uncertain behavior of an environment.
Software verification tools assume that invoked functions without definitions can return any possible value of their
return types and do not have any side effects.
Often users can agree with these implicit models especially taking into account that development of explicit models can
take much time.
For instance, this may be the case for functions that make debug printing and logging (at this stage we are not intended
to check possible rules of usage of those APIs as well their implementations).
Sometimes software verification tools can report false alarms or miss bugs, e.g. when invoked functions allocate memory,
initialize it and return pointers to it.
You should develop *common API models* if you are not satisfied with obtained verification results and if you have time
for that.
In addition to reducing obscure behavior you can leverage the same approach to decline a complexity of some internal
APIs of considered program fragments.
For instance, when the target program fragment contains a big loop that boundary depends on a value of an internal
macro, you can try to decrease that value by developing an appropriate model.

Development of common API models is very similar to :ref:`dev_req_specs`.
Here we will focus on some specific issues and tricks without repeating how to develop API models.
You should enumerate additional common API models as a value of attribute **common models** of RSG plugin options within
an appropriate requirement specifications base.
It is necessary to keep in mind that common API models will be used for all requirement specifications unlike models
developed for particular requirement specifications.

For functions without definitions you can omit aspect files since you can provide corresponding common API models as
definitions of those functions.
This way may be faster and easier but you should remember that one day your model can vanish suddenly due to function
definitions will be considered as a part of target program fragments.
For functions with definitions and for macros you have to develop aspect files anyway.

Regarding file names, we recommend following the same rules as for models for requirement specifications.
In case of conflicts, i.e. when you need both common model and requirements specification model for the same API and,
thus, the same file name, you should use suffix **.common.c** for the former.
In case of such conflicts you can also have coinciding names of model functions, say, when you need to develop a model
for a given function and check for its usage simultaneously.
Moreover, this may be the case due to models for some functions, e.g. registration and deregistration ones, are defined
within the generated environment model already.
You have to define models with unique names and relate them with each other in such the way that will not prevent their
original intention.

The last but not the least advice:

* Look at existing common API models.
  They can help you to learn the specific syntax as well as to investigate some particular working decisions.
* You should accurately model possible error behavior of modeled APIs.
  Otherwise, corresponding error handling paths will not be considered at verification that can lead to missing bugs.
* Do not forget to test your common API models like requirement specifications.

Example of Common API Model
---------------------------

Let’s consider an example of development of a common API model.
In the Linux kernel there is function :c:func:`kzalloc()`.
This is a vital function since a lot of loadable kernel modules use it and it affects subsequent execution paths very
considerably.
Moreover, it is necessary to check that callers invoke this function in the atomic context when passing **GFP_ATOMIC**
as a value of argument **flags**.

.. c:function:: static inline void *kzalloc(size_t size, gfp_t flags)

    Allocate memory and initialize it with zeroes.

    :param size: The size of memory to be allocated.
    :param flags: The type of memory to be allocated.
    :return: The pointer to the allocated and initialized memory in case of success and NULL otherwise.

The :c:func:`kzalloc()` model can look as follows:

.. code-block:: c

     #include <linux/types.h>
     #include <ldv/linux/common.h>
     #include <ldv/linux/slab.h>
     #include <ldv/verifier/memory.h>

     void *ldv_kzalloc(size_t size, gfp_t flags)
     {
         void *res;

         ldv_check_alloc_flags(flags);
         res = ldv_zalloc(size);

         return res;
     }

Above we included several headers in the model:

* :file:`ldv/linux/common.h` holds a declaration for **ldv_check_alloc_flags()**.
  Its definition may be provided by appropriate requirement specifications.
* :file:`ldv/linux/slab.h` contains a declaration for a model function itself.
  Its possible content is demonstrated below.
* :file:`ldv/verifier/memory.h` describes a bunch of memory allocation function models.
  In particular, **ldv_zalloc()** behaves exactly as :c:func:`kzalloc()` without paying any attention to **flags**.

.. code-block:: c

     #ifndef __LDV_LINUX_SLAB_H
     #define __LDV_LINUX_SLAB_H

     #include <linux/types.h>

     extern void *ldv_kzalloc(size_t size, gfp_t flags);

     #endif /* __LDV_LINUX_SLAB_H */

We have to develop the aspect file since :c:func:`kzalloc()` is a static inline function, i.e. it will have the
definition always.
The aspect file may be so:

.. code-block:: c

     before: file("$this")
     {
     #include <ldv/linux/slab.h>
     }


     around: execution(static inline void *kzalloc(size_t size, gfp_t flags))
     {
         return ldv_kzalloc(size, flags);
     }
