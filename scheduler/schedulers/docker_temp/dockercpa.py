# todo: что тебе мешает посмотреть как сделано у нас и сделать также? Приставка ниже говорит, что ты запускаешь python2.7, а у нас весь клевер на 3.4-3.6
#!/usr/bin/python

import os
import re
# todo: жаль что библиотека ниже не используется -_- Все аргументы нужно брать через нее.
import argparse
import json
# todo: испорты лучше делать не так, а чтобы вызовы были subprocess.run и т.п. Так хоть понятно, что это функция снаружи, особенно это полезно для больших скриптов и программ, которые ты в будующем будешь писать
from subprocess import run, Popen, PIPE


# todo: что за скрипт без глобального кода для выполнения? Кто начнет выполнение функции ниже? Ты его надеюсь запускал ... Опять же посмотри как у нас сделано.

# todo: ЗАМЕЧАНИЕ ПО СУТИ: 1. зависимости для работы клевер взяты не все. Не хвататет cil, cif.
# todo: ЗАМЕЧАНИЕ ПО СУТИ: 2. Не хватает скрипта для запуска core и cpachecker - ну ты и сам это знаешь. Без этого образы пока нерабочие.
# todo: ЗАМЕЧАНИЕ ПО СУТИ: 3. Нужен знатный рефакторинг кода ниже. Для каждого проекта, кроме сборки cpachecker делается одно и то же, поэтому копирование и установку можно делать единообразно, а не кучей копипасты.

def prepare_enviroment_and_dockerfile(config_file=None, configuration=None):
    """
    :param config_file: File with the configuration. Do not set the option alongside with the configuration one.
    :param configuration: The configuration dictionary. Do not set the option alongside with the file one.
    :return: #hamster CHECK:
    """
    # todo: Дописал бы уж, раз вставил пайдок


    # check configuration being
    # todo: argparse как раз поможет это сделать элегантнее
    if configuration and config_file:
        raise ValueError('Provide either file or configuration string')
    elif config_file:
        with open(config_file, encoding="utf8") as _fh:
            config = json.loads(_fh.read())
    elif configuration:
        config = configuration
    else:
        raise ValueError('Provide any file or configuration string')

    # check image config
    # todo: "image config" not in config - так правильно, это относится к коду ниже
    if not "image config" in config:
        raise KeyError("Provide configuration property 'image config' as an JSON-object")

    # check image base - image_base
    if not "image base" in config["image config"]:
        raise KeyError("Provide configuration property 'image base' as an JSON-object")
    # check empty value
    elif config["image config"]["image base"]:
        image_base = config["image config"]["image base"]
    else:
        image_base = "debian:latest"

    # check path
    # check path type - image_path_type
    # todo: немонимаю зачем это все - перемещайся в директорию указанную в build path на пофиг, какая разница абсолютный или относительный это путь, просто проверь что переход можно сделать и все. Но Сначала можно преобразовать все остальные пути из конфига до абсолютных или относительных для build dir
    if not "path type" in config["image config"]:
        raise KeyError("Provide configuration property 'path type' as an JSON-object")
    # check build path - image_build_path
    elif not "build path" in config["image config"]:
        raise KeyError("Provide configuration property 'build path' as an JSON-object")
    else:
        image_path_type = config["image config"]["path type"]
        if image_path_type not in ('absolute', 'relative'):
            raise ValueError("Provide right path type")
        else:
            #       image_path_val = True if path relative
            # and   image_path_val = False if absolute
            image_path_val = image_path_type == "relative"
        image_build_path = config["image config"]["build path"]
        if (not image_path_val and not image_build_path[0] == '/') or (
                image_path_val and image_build_path[0] == '/'):
            raise ValueError(
                "Check build_path: if it absolute then start with '/' else if it relative then start without '/'")

    # check port - image_port
    if not "port" in config["image config"]:
        raise KeyError("Provide configuration property 'port' as an JSON-object")
    # check empty value
    elif config["image config"]["port"]:
        image_port = config["image config"]["port"]
    else:
        raise ValueError("Provide existing port in configuration")

    # check Klever Core information
    if not "Klever Core" in config["image config"]:
        raise KeyError("Provide configuration property 'Klever Core' as an JSON-object")
        # check do we need Klever Core in image
    elif not "using" in config["image config"]["Klever Core"]:
        raise KeyError("Provide configuration property 'Klever Core''using' as an JSON-object")
    elif config["image config"]["Klever Core"]["using"]:
        klever_using = True
        # check Klever Core version
        if not "version" in config["image config"]["Klever Core"]:
            raise KeyError("Provide configuration property 'Klever Core''version' as an JSON-object")
        elif not "path" in config["image config"]["Klever Core"]:
            raise KeyError("Provide configuration property 'Klever Core''path' as an JSON-object")
        elif not "executable path" in config["image config"]["Klever Core"]:
            raise KeyError("Provide configuration property 'Klever Core''executable path' as an JSON-object")
        else:
            klever_version = config["image config"]["Klever Core"]["version"]
            klever_path = config["image config"]["Klever Core"]["path"]
            klever_exec_path = config["image config"]["Klever Core"]["executable path"]
    else:
        klever_using = False

    # check CPAchecker information
    if not "CPAchecker" in config["image config"]:
        raise KeyError("Provide configuration property 'CPAchecker' as an JSON-object")
    # check do we need CPAchecker in image
    elif not "using" in config["image config"]["CPAchecker"]:
        raise KeyError("Provide configuration property 'CPAchecker''using' as an JSON-object")
    elif config["image config"]["CPAchecker"]["using"]:
        cpachecker_using = True
        # check name of archive with CPAchecker binaries
        if not "tar name" in config["image config"]["CPAchecker"]:
            raise KeyError("Provide configuration property 'CPAchecker''tar name' as an JSON-object")
        # check CPAchecker version: branch and revision
        elif not "version" in config["image config"]["CPAchecker"]:
            raise KeyError(
                "Provide configuration property 'CPAchecker''version' as an JSON-object")
        # check CPAchecker path
        elif not "path" in config["image config"]["CPAchecker"]:
            raise KeyError("Provide configuration property 'CPAchecker''path' as an JSON-object")
        # check CPAchecker executable path
        elif not "executable path" in config["image config"]["CPAchecker"]:
            raise KeyError("Provide configuration property 'CPAchecker''executable path' as an JSON-object")
        else:
            cpachecker_tar_name = config["image config"]["CPAchecker"]["tar name"]
            cpachecker_version = config["image config"]["CPAchecker"]["version"]
            if ":" in cpachecker_version:
                cpachecker_branch_name, cpachecker_branch_revision = cpachecker_version.split(
                    ':')
                # if branch name not trunk, then add "branches/" in the begining to switch on this branch right
                if not cpachecker_branch_name == "trunk":
                    cpachecker_branch_name = "branches/" + cpachecker_branch_name
            # if not branch name, then use trunk
            else:
                cpachecker_branch_name = "trunk"
                cpachecker_branch_revision = cpachecker_version
            # check that revision is number
            if not cpachecker_branch_revision.isdigit():
                raise ValueError("Integer branch revision is expected")
            cpachecker_path = config["image config"]["CPAchecker"]["path"]
            cpachecker_exec_path = config["image config"]["CPAchecker"]["executable path"]
    else:
        cpachecker_using = False

    # check BenchExec information
    # todo: не нужно проверять using - он всегда нужен раз уж на то пошло
    if not "BenchExec" in config["image config"]:
        raise KeyError("Provide configuration property 'BenchExec' as an JSON-object")
    # check do we need BenchExec in image
    elif not "using" in config["image config"]["BenchExec"]:
        raise KeyError("Provide configuration property 'BenchExec''using' as an JSON-object")
    elif config["image config"]["BenchExec"]["using"]:
        benchexec_using = True
        # check BenchExec version
        if not "version" in config["image config"]["BenchExec"]:
            raise KeyError("Provide configuration property 'BenchExec''version' as an JSON-object")
        elif not "path" in config["image config"]["BenchExec"]:
            raise KeyError("Provide configuration property 'BenchExec''path' as an JSON-object")
        elif not "executable path" in config["image config"]["BenchExec"]:
            raise KeyError("Provide configuration property 'BenchExec''executable path' as an JSON-object")
        else:
            benchexec_version = config["image config"]["BenchExec"]["version"]
            benchexec_path = config["image config"]["BenchExec"]["path"]
            benchexec_exec_path = config["image config"]["BenchExec"]["executable path"]
    else:
        benchexec_using = False


    # configure enviroment

    # check current directory
    current_path = os.path.curdir
    # remember initial directory
    init_path = current_path

    # pass to working path - image_build_path
    if image_path_val:  # if path relative
        current_path = os.path.join(current_path, image_build_path)
    else:
        current_path = image_build_path
    # save current build path
    full_build_path = current_path
    os.chdir(current_path)

    # configure enviroment Klever Core
    if klever_using:
        # pass to CPAchecker path
        current_path = os.path.join(full_build_path, klever_path)
        os.chdir(current_path)

        # save git branch
        # todo: используй наши утилиты из scheduler/utils например get_output или более сложный execute - у тебя замороченно и много лишнего. Напримрер зачем явно создавать процесс, если тебе не нужно параллельное выполнение, а нужно просто получить результат работы команды?
        _process = Popen("git status", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        _process_output, _process_error = _process.communicate()
        if _process_error:
            raise RuntimeError("Error then execute shell command 'git status': {}".format(_process_error))
        # search name of current branch
        temp_branch_klever = re.search(r"On branch .*", _process_output)
        if temp_branch_klever:
            saved_branch_klever = temp_branch_klever.group(0).split()[2]
        else:
            raise RuntimeError("Can't find branch name in the output of 'git status' shell command:\n{}".format(
                _process_output))

        # switch on right git branch
        _cmd = "git checkout " + klever_version
        run(_cmd, shell=True)

    # configure enviroment CPAchecker
    if cpachecker_using:
        # todo: конечно коряво, два варианта же trunk или branches/*** - тут чего-то полно конфигураций, имен архивов и т.д.
        # pass to CPAchecker path
        current_path = os.path.join(full_build_path, cpachecker_path)
        os.chdir(current_path)

        # save current svn branch
        _process = Popen("svn info", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        _process_output, _process_error = _process.communicate()
        if _process_error:
            raise RuntimeError("Error then execute shell command 'svn info': {}".format(_process_error))
        # seach current branch name
        temp_branch_cpachecker = re.search(r"Relative URL: \^/.*", _process_output)
        if temp_branch_cpachecker:
            saved_branch_cpachecker = temp_branch_cpachecker.group(0).split()[2]
        else:
            raise RuntimeError("Can't find 'relative URL' in the output of 'svn info' shell command:\n{}".format(
                _process_output))
        # seach current branch revision
        temp_revision_cpachecker = re.search(r"Revision: [0-9]+", _process_output)
        if temp_revision_cpachecker:
            saved_revison_cpachecker = temp_revision_cpachecker.group(0).split()[1]
        else:
            raise RuntimeError(
                "Can't find 'revision' in the output of 'svn info' shell command:\n{}".format(_process_output))

        # switch on right svn branch and revision
        # todo: велосипедыыы Нужно будет переделать на основе биндинга python3-svn
        _cmd = "svn switch ^/" + cpachecker_branch_name
        run(_cmd, shell=True)
        _cmd = "svn up -r " + cpachecker_branch_revision
        run(_cmd, shell=True)

        # make cpachecker .tar.bz2 archive
        _cmd = "ant tar"
        run(_cmd, shell=True)

        # check archive name
        _process = Popen("ls", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        _process_output, _process_error = _process.communicate()
        if _process_error:
            raise RuntimeError("Error then execute shell command 'ls': {}".format(_process_error))
        # seach full archive name
        temp_archive_name = re.search(r"CPAchecker.*tar\.bz2", _process_output)
        if temp_archive_name:
            archive_name = temp_archive_name.group(0)
            if not archive_name == cpachecker_tar_name:
                raise ValueError("Wrong CPAchecker tar name in config, right name:{}".format(archive_name))
        else:
            raise RuntimeError("Can't find CPAchecker tar archive name in the output of 'ls' shell command:\n{}".format(
                _process_output))

    # configure enviroment BenchExec
    if benchexec_using:
        # pass to CPAchecker path
        current_path = os.path.join(full_build_path, benchexec_path)
        os.chdir(current_path)

        # save git branch
        _process = Popen("git status", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
        _process_output, _process_error = _process.communicate()
        if _process_error:
            raise RuntimeError("Error then execute shell command 'git status': {}".format(_process_error))
        # search name of current branch
        temp_branch_name_benchexec = re.search(r"On branch .*", _process_output)
        if temp_branch_name_benchexec:
            saved_branch_name_benchexec = temp_branch_name_benchexec.group(0).split()[2]
        else:
            raise RuntimeError("Can't find branch name in the output of 'git status' shell command:\n{}".format(
                _process_output))

        # switch on right git branch
        _cmd = "git checkout " + benchexec_version
        run(_cmd, shell=True)

    # generation dockerfile
    current_path = full_build_path
    os.chdir(current_path)
    # make dockerfile and write into it
    # todo: тут конечно чрезмерный хардкод. Особенно с пакетами. В будующем нужно отрефакторить и сделать переиспользование скрипта, устанавливающего зависимости.
    # todo: остальные замечения я оставил в примере докерфайла
    with open("dockerfile", "w", encoding="utf8") as dockerfile:
        _str = "#Installing parts: "
        if klever_using:
            _str = _str + "Klever Core | "
        if cpachecker_using:
            _str = _str + "CPAchecker | "
        if benchexec_using:
            _str = _str + "BenchExec | "
        _str = _str + "\n"
        dockerfile.write(_str)
        # core system
        _str = "FROM " + image_base + "\n"
        dockerfile.write(_str)
        # enviroment
        _str = '\nENV DEBIAN_FRONTEND = "noninteractive"\n'
        dockerfile.write(_str)

        _str = "\n# Upgrade installed packages\n"
        dockerfile.write(_str)
        _str = "RUN apt-get update && apt-get upgrade -y\n"
        dockerfile.write(_str)

        _str = "\n# Install new packages\n"
        dockerfile.write(_str)
        _str = "RUN apt-get update && apt-get install -y \\\n"
        dockerfile.write(_str)
        if klever_using:
            _str = "# For Python packages\n"
            dockerfile.write(_str)
            _str = "   libpq-dev python3-dev python3-pip \\\n"
            dockerfile.write(_str)
            _str = "# For Klever Core\n"
            dockerfile.write(_str)
            _str = "   bc git graphviz \\\n"
            dockerfile.write(_str)
        if cpachecker_using:
            _str = "# For CPAchecker 1.6+\n"
            dockerfile.write(_str)
            _str = "   openjdk-8-jre-headless \\\n"
            dockerfile.write(_str)
        _str = "# For building the Linux kernel\n"
        dockerfile.write(_str)
        _str = "   make libc6-dev-i386 \\\n"
        dockerfile.write(_str)
        _str = "# For building new versions of the Linux kernel\n"
        dockerfile.write(_str)
        _str = "   libssl-dev libelf-dev\n"
        dockerfile.write(_str)

        if klever_using:
            _str = "\n# Install Python packages\n"
            dockerfile.write(_str)
            _str = "RUN pip3 install -U \\\n"
            dockerfile.write(_str)
            _str = "# For Klever Core\n"
            dockerfile.write(_str)
            _str = "   jinja2 graphviz ply requests setuptools_scm \\\n"
            dockerfile.write(_str)
            _str = "# For Klever Scheduler\n"
            dockerfile.write(_str)
            _str = "   consulate\n"
            dockerfile.write(_str)
            _str = "\n# Copy Klever Core binaries\n"
            dockerfile.write(_str)
            _str = "COPY " + klever_path + " klever/core\n"
            dockerfile.write(_str)
            _str = "\nENV PATH klever/core/" + klever_exec_path + ":$PATH\n"
            dockerfile.write(_str)

        if cpachecker_using:
            _str = "\n# Copy CPAchecker binaries\n"
            dockerfile.write(_str)
            _str = "# ADD will auto extract archive\n"
            dockerfile.write(_str)
            _str = 'ADD ["' + archive_name + '", "/"]\n'
            dockerfile.write(_str)
            _str = '\nENV PATH="' + archive_name.split(".tar.")[0] + '/' + cpachecker_exec_path + ':{$PATH}"\n'
            dockerfile.write(_str)

        if benchexec_using:
            _str = "\n# Copy BenchExec source code\n"
            dockerfile.write(_str)
            _str = "COPY " + benchexec_path + "/bin benchexec/bin\n"
            dockerfile.write(_str)
            _str = "COPY " + benchexec_path + "/benchexec benchexec/benchexec\n"
            dockerfile.write(_str)
            _str = "\nENV PATH benchexec/" + benchexec_exec_path + ":$PATH\n"
            dockerfile.write(_str)

        _str = "\n# Expose port\n"
        dockerfile.write(_str)
        _str = "EXPOSE " + str(image_port) + "\n"
        dockerfile.write(_str)

        _str = "\n# Copy Klever scheduler to run client scr\n"
        dockerfile.write(_str)
        _str = "COPY klever/scheduler klever/scheduler\n"
        dockerfile.write(_str)
        _str = "WORKDIR /root/klever/scheduler/client\n"
        dockerfile.write(_str)
        _str = 'ENTRYPOINT ["python", "node_client.py"]\n'
        dockerfile.write(_str)

    # generation .dockerignore
    with open(".dockerignore", "w", encoding="utf8") as dockerignore:
        _str = '*.git*\n'
        dockerignore.write(_str)
        _str = '*.svn*\n'
        dockerignore.write(_str)
