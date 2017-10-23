import core.utils


def cif_execute(logger, params, env=None, cwd=None):
    try:
        core.utils.execute(logger, params, env, cwd=cwd)
    except core.utils.CommandError as e:
        lines = []
        # Read until first 'error' line
        with open('problem desc.txt') as fp:
            for line in fp.readlines():
                lines.append(line)
                if 'error:' in line:
                    break
        with open('problem desc.txt', 'w', encoding='utf-8') as fp:
            fp.write(''.join(lines))

        raise e

