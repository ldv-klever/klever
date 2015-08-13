import hashlib
from marks.models import MarkDefaultFunctions, MarkUnsafeCompare,\
    MarkUnsafeConvert


def populate_functions():
    compare_func = MarkUnsafeCompare()
    compare_func.body = '\n'.join([
        'import random',
        'return random.random()',
    ])
    compare_func.description = "Function for comparing reports, returns random"
    compare_func.name = "compare_unsafes"
    compare_func.hash_sum = hashlib.md5(
        (compare_func.name + compare_func.body).encode('utf8')
    ).hexdigest()
    compare_func.save()

    compare_func = MarkUnsafeCompare()
    compare_func.body = 'return 1'
    compare_func.description = "Function for comparing reports, returns 1"
    compare_func.name = "compare_unsafes_def"
    compare_func.hash_sum = hashlib.md5(
        (compare_func.name + compare_func.body).encode('utf8')
    ).hexdigest()
    compare_func.save()

    convert_func = MarkUnsafeConvert()
    convert_func.body = 'return error_trace'
    convert_func.description = "Function for converting trace, just copy"
    convert_func.name = "default_convert"
    convert_func.save()

    def_funcs = MarkDefaultFunctions()
    def_funcs.compare = compare_func
    def_funcs.convert = convert_func
    def_funcs.save()
