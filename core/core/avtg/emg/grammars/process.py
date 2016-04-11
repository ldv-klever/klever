__process_grammar = \
'''
(* Main expression *)
FinalProcess = (Operators | Bracket)$;
Operators = Switch | Sequence;

(* Signle process *)
Process = Null | ReceiveProcess | SendProcess | SubprocessProcess | ConditionProcess | Bracket;
Null = null:'0';
ReceiveProcess = receive:Receive;
SendProcess = dispatch:Send;
SubprocessProcess = subprocess:Subprocess;
ConditionProcess = condition:Condition;
Receive = '('[replicative:'!']name:identifier[number:Repetition]')';
Send = '['[broadcast:'@']name:identifier[number:Repetition]']';
Condition = '<'name:identifier[number:Repetition]'>';
Subprocess = '{'name:identifier'}';

(* Operators *)
Sequence = sequence:SequenceExpr;
Switch = options:SwitchExpr;
SequenceExpr = @+:Process{'.'@+:Process}*;
SwitchExpr = @+:Sequence{'|'@+:Sequence}+;

(* Brackets *)
Bracket = process:BracketExpr;
BracketExpr = '('@:Operators')';

(* Basic expressions and terminals *)
Repetition = '['@:(number | label)']';
identifier = /\w+/;
number = /\d+/;
label = /%\w+%/;
'''
__process_model = None


def __undefaulted(x, tp):
    if isinstance(x, list):
        return [__undefaulted(element, tp) for element in x]
    elif isinstance(x, tp):
        return dict((k, __undefaulted(v, tp)) for (k, v) in x.iteritems())
    else:
        return x


def __check_grammar():
    global __process_model

    if not __process_model:
        import grako
        __process_model = grako.genmodel('process', __process_grammar)


def parse_process(string):
    __check_grammar()
    ast = __process_model.parse(string, ignorecase=True)
    ast = __undefaulted(ast, type(ast))

    return ast

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'