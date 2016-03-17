import re

WHOLE_INDENT = re.compile('^(\s*)')

INDENT = re.compile('[ ]{2}|\t')

DECLARATION = re.compile('declaration:[ ]([^;]+);[ ]path: ([^\n]+)')

EXPLICIT_VALUE = re.compile('value:[ ]([^\n]+)')

LIST_VALUE = re.compile('value:')

ARRAY_ELEMENT_INDEX = re.compile('array[ ]element[ ]index:[ ]([^\n]+)')

FIELD_DECLARATION = re.compile('field[ ]declaration:[ ]([^\n]+)')


def lexer(line):
    # Remove indent
    token = {'indent': 0}
    if INDENT.match(line):
        token['indent'] = len(INDENT.findall(WHOLE_INDENT.match(line).group(1)))
    line = line.strip()

    if DECLARATION.match(line):
        token['declaration'] = DECLARATION.match(line).group(1)
        token['path'] = DECLARATION.match(line).group(2)
    elif EXPLICIT_VALUE.match(line):
        token['value'] = EXPLICIT_VALUE.match(line).group(1)
    elif FIELD_DECLARATION.match(line):
        token['field'] = FIELD_DECLARATION.match(line).group(1)
    elif ARRAY_ELEMENT_INDEX.match(line):
        token['index'] = int(ARRAY_ELEMENT_INDEX.match(line).group(1))
    elif LIST_VALUE.match(line):
        token['value'] = []
    else:
        raise ValueError('Cannot parse line {}'.format(line))

    return token


def parse(tokens):
    ast = []
    while len(tokens) > 0:
        declaration = tokens.pop(0)
        if type(tokens[0]['value']) is list and len(tokens) > 1 and tokens[1]['indent'] == declaration['indent'] + 1:
            declaration['value'] = extract_list(tokens, 0, declaration['indent'] + 1)
        else:
            declaration['value'] = tokens[0]['value']
        del tokens[0]
        del declaration['indent']
        ast.append(declaration)
    return ast


def extract_list(tokens, index, level):
    value = []
    stop = False
    while not stop:
        if len(tokens) > 2:
            token = tokens[index + 1]
            if 'field' in token or 'index' in token:
                if token['indent'] == level:
                    if type(tokens[index + 2]['value']) is list and len(tokens) > index + 3 and \
                            tokens[index + 3]['indent'] == token['indent'] + 1:
                        token['value'] = extract_list(tokens, index + 2, token['indent'] + 1)
                    else:
                        token['value'] = tokens[index + 2]['value']

                    del token['indent']
                    del tokens[index + 2]
                    del tokens[index + 1]
                    value.append(token)
                else:
                    stop = True
            else:
                stop = True
        else:
            stop = True
    return value


def parse_initializations(file):
    with open(file) as fd:
        tokens = [lexer(line) for line in fd.readlines()]
    return parse(tokens)

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'


