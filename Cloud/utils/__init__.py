import os


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

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
