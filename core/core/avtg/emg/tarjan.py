def calculate_load_order(logger, modules):
    sorted_list = []

    unmarked = list(sorted(list(modules)))
    marked = {}
    while(unmarked):
        selected = unmarked.pop(0)
        if selected not in marked:
            visit(logger, selected, marked, sorted_list, modules)

    return sorted_list


def visit(logger, selected, marked, sorted_list, modules):
    if selected in marked and marked[selected] == 0:
        logger.debug('Given graph is not a DAG')

    elif selected not in marked:
        marked[selected] = 0

        if selected in modules:
            for m in modules[selected]:
                visit(logger, m, marked, sorted_list, modules)

        marked[selected] = 1
        sorted_list.append(selected)
