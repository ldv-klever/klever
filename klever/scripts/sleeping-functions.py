import argparse
import sys

from clade import Clade


def is_void(sign):
    signature = sign
    while signature.startswith("static") or signature.startswith("inline"):
        # 6 + 1 for space
        signature = signature[7:]

    return signature.startswith("void") and not signature.startswith("void *")


def get_callers(funcs, callgraph):
    caller_funcs = {}
    for funcs_in_file in callgraph.values():
        for func in funcs:
            if func in funcs_in_file:
                # Add the sleep function itself
                if 'calls' in funcs_in_file[func]:
                    for file2, desc in funcs_in_file[func]['calls'].items():
                        if func in desc:
                            caller_funcs[file2] = [func]

                # Add its callers
                if 'called_in' in funcs_in_file[func]:
                    for file2 in funcs_in_file[func]['called_in']:
                        caller_funcs[file2] = list(funcs_in_file[func]['called_in'][file2].keys())
    return caller_funcs


def main(build_base_path, output, depth):

    clade = Clade(work_dir=build_base_path, conf={}, preset="base")
    callgraph = clade.get_callgraph()

    funcs = ("__might_sleep", "msleep", "usleep_range")
    caller_funcs = {}
    for _ in range(depth):
        caller_funcs = get_callers(funcs, callgraph)
        funcs = set()
        for funcs_in_file in caller_funcs.values():
            funcs.update(funcs_in_file)

    func_defs_void = []
    func_defs_not_void = []

    functions_def = clade.get_functions_by_file(list(caller_funcs.keys()))
    for file, funcs in caller_funcs.items():
        if file in functions_def:
            for func in funcs:
                if func in functions_def[file]:
                    sign = functions_def[file][func]['signature']
                    if '[' in sign:
                        # TODO: Klever doesn't understand constructions in prototypes like int a[8u]
                        continue
                    if is_void(sign):
                        func_defs_void.append('call({})'.format(sign[:-1]))
                    else:
                        func_defs_not_void.append('call({})'.format(sign[:-1]))
                else:
                    print("Missed function ", func)
        else:
            print("Missed file ", file)

    func_defs_void.sort()
    func_defs_not_void.sort()

    with open(output, 'w') as f:
        f.write('/*\n* Copyright (c) 2024 ISP RAS (http://www.ispras.ru)\n')
        f.write('* Ivannikov Institute for System Programming of the Russian Academy of Sciences\n*\n')
        f.write('* Licensed under the Apache License, Version 2.0 (the "License");\n')
        f.write('* you may not use this file except in compliance with the License.\n')
        f.write('* You may obtain a copy of the License at\n*\n')
        f.write('*   http://www.apache.org/licenses/LICENSE-2.0\n*\n')
        f.write('* Unless required by applicable law or agreed to in writing, software\n')
        f.write('* distributed under the License is distributed on an "AS IS" BASIS,\n')
        f.write('* WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.\n')
        f.write('* See the License for the specific language governing permissions and\n')
        f.write('* limitations under the License.\n*/\n')

        f.write('\n/*== This file is generated automatically by scripts/sleeping-functions.py ==*/\n\n')

        f.write('before: file("$this")\n{\n')
        f.write('\textern void ldv_common_sleep(void);\n}\n')

        f.write('\npointcut SLEEP_VOID: ')
        f.write(' ||\n\t'.join(func_defs_void))
        f.write('\n\n')

        f.write('\npointcut SLEEP_NOT_VOID: ')
        f.write(' ||\n\t'.join(func_defs_not_void))
        f.write('\n\n')

        f.write('before: SLEEP_NOT_VOID\n{\n')
        f.write('\tldv_common_sleep();\n')
        f.write('\treturn 0;\n}\n\n')

        f.write('before: SLEEP_VOID\n{\n')
        f.write('\tldv_common_sleep();\n}')


if __name__ == '__main__':
    parser = argparse.ArgumentParser()

    parser.add_argument(
        '-b',
        '--build-base',
        help='path to the directory where build base is stored',
        metavar='PATH'
    )

    parser.add_argument(
        '-o',
        '--output',
        help='path to the output aspect file. Default: {!r}'.format('common.aspect'),
        default='common.aspect',
        metavar='PATH'
    )

    parser.add_argument(
        '-d',
        '--depth',
        help='Depth of a search of callers. Default: 1',
        default=1,
        type=int
    )

    args = parser.parse_args(sys.argv[1:])
    if args.build_base:
        main(args.build_base, args.output, args.depth)
    else:
        print("No build base specified")
        sys.exit(-1)
