.. Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
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

:orphan:

Glossary
========

.. glossary::

    $KLEVER_SRC
        A path to a root directory of Klever source tree.

    $KLEVER_DEPLOY_DIR
        A path to a directory where Klever should be deployed. Although this directory can be one of standard ones
        like :file:`/usr/local/bin` or :file:`/bin`, it is recommended to use some specific one.

    $SSH_RSA_PRIVATE_KEY_FILE
        A path to a file with SSH RSA private key. It is not recommended to use your sensitive keys. Instead either
        create and use a specific one or use keys that are accepted in your groups to enable an access to other group
        members.

    $INSTANCES
        A number of OpenStack instances to be deployed.
