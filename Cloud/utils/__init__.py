import os
import subprocess
def split_archive_name(path):
    """
    Split archive name into file name and extension. The difference with is.path.splitext is that this function can
    properly parse double zipped archive names like myname.tar.gz providing "myname" and ".tar.gz". Would not work
    properly with names which contain dots.
    :param path: File path or file name.
    :return: tuple with file name at the first position and extension within the second one.
    """
    name = path
    extension = ""
    while "." in name:
        split = os.path.splitext(name)
        name = split[0]
        extension = split[1] + extension

    return name, extension


def get_output(command):
    """
    Return STDOUT of the command.
    :param command: a command to be executed to get an entity value.
    """
    val = subprocess.getoutput(command)
    if not val:
        raise ValueError('Cannot get anything executing {}'.format(command))

    return val


def extract_system_information():
    """
    Extract information about the system and return it as a dictionary.
    :return: dictionary with system info,
    """
    system_conf = {}
    system_conf["node name"] = get_output('uname -n')
    system_conf["CPU model"] = get_output('cat /proc/cpuinfo | grep -m1 "model name" | sed -r "s/^.*: //"')
    system_conf["CPU number"] = int(get_output('cat /proc/cpuinfo | grep processor | wc -l'))
    system_conf["RAM memory"] = \
        int(get_output('cat /proc/meminfo | grep "MemTotal" | sed -r "s/^.*: *([0-9]+).*/1024 * \\1/" | bc'))
    system_conf["disk memory"] = 1024 * int(get_output('df ./ | grep / | awk \'{ print $4 }\''))
    system_conf["Linux kernel version"] = get_output('uname -r')
    system_conf["arch"] = get_output('uname -m')
    return system_conf

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'