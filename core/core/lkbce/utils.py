import re


def get_deps_from_gcc_deps_file(deps_file):
    deps = []

    with open(deps_file, encoding='ascii') as fp:
        match = re.match(r'[^:]+:(.+)', fp.readline())
        if match:
            first_dep_line = match.group(1)
        else:
            raise AssertionError('Dependencies file has unsupported format')

        for dep_line in [first_dep_line] + fp.readlines():
            dep_line = dep_line.lstrip(' ')
            dep_line = dep_line.rstrip(' \\\n')
            if not dep_line:
                continue
            deps.extend(dep_line.split(' '))

    return deps
