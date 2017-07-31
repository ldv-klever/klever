#!/usr/bin/python3

import re
import os

from xml.dom import minidom


def process_et(logger, specified_error_trace):

    try:
        with open(specified_error_trace, encoding='ascii') as fp:
            dom = minidom.parse(fp)
    except:
        # TODO: create additional unknown report here, but do not fail completely. (MEA)
        return

    graphml = dom.getElementsByTagName('graphml')[0]

    logger.debug('Get source files referred by error trace')
    src_files = set()
    for key in graphml.getElementsByTagName('key'):
        if key.getAttribute('id') == 'originfile':
            default_elem = key.getElementsByTagName('default')
            if default_elem:
                default = key.getElementsByTagName('default')[0]
                default_src_file = default.firstChild.data
                src_files.add(default_src_file)
            else:
                default_src_file = 'cil.i'
                src_files.add(default_src_file)
    graph = graphml.getElementsByTagName('graph')[0]
    for edge in graph.getElementsByTagName('edge'):
        for data in edge.getElementsByTagName('data'):
            if data.getAttribute('key') == 'originfile':
                # Internal automaton variables do not have a source file.
                if data.firstChild:
                    src_files.add(data.firstChild.data)

    logger.debug('Extract notes and warnings from source files referred by error trace')
    notes = {}
    warns = {}
    for src_file in src_files:

        if not os.path.isfile(src_file):
            break
            # raise FileNotFoundError(
            #    'File "{0}" referred by error trace does not exist'.format(src_file))

        with open(src_file, encoding='utf8') as fp:
            src_line = 0
            for line in fp:
                src_line += 1
                match = re.search(
                    r'/\*\s+(MODEL_FUNC_DEF|ASPECT_FUNC_CALL|ASSERT|CHANGE_STATE|RETURN|MODEL_FUNC_CALL|OTHER)\s+(.*)\s+\*/',
                    line)
                # TODO: should be improved
                # if strategy.:
                #    match = re.search(r'/\*\s+(ASPECT_FUNC_CALL)\s+(.*)\s+\*/', line)
                if match:
                    kind, comment = match.groups()

                    if kind == 'MODEL_FUNC_DEF':
                        # Get necessary function name located on following line.
                        try:
                            line = next(fp)
                            # Don't forget to increase counter.
                            src_line += 1
                            match = re.search(r'(ldv_\w+)', line)
                            if match:
                                func_name = match.groups()[0]
                            else:
                                raise ValueError(
                                    'Model function definition is not specified in "{0}"'.format(line))
                        except StopIteration:
                            raise ValueError('Model function definition does not exist')
                        notes[func_name] = comment
                    else:
                        if src_file not in notes:
                            notes[src_file] = {}
                        notes[src_file][src_line + 1] = comment
                        # Some assert(s) will become warning(s).
                        if kind == 'ASSERT':
                            if src_file not in warns:
                                warns[src_file] = {}
                            warns[src_file][src_line + 1] = comment

    logger.debug('Add notes and warnings to error trace')
    # Find out sequence of edges (violation path) from entry node to violation node.
    violation_edges = []
    entry_node_id = None
    violation_node_id = None
    for node in graph.getElementsByTagName('node'):
        for data in node.getElementsByTagName('data'):
            if data.getAttribute('key') == 'entry' and data.firstChild.data == 'true':
                entry_node_id = node.getAttribute('id')
            elif data.getAttribute('key') == 'violation' and data.firstChild.data == 'true':
                violation_node_id = node.getAttribute('id')
    src_edges = {}
    for edge in graph.getElementsByTagName('edge'):
        src_node_id = edge.getAttribute('source')
        dst_node_id = edge.getAttribute('target')
        src_edges[dst_node_id] = (src_node_id, edge)
    cur_src_edge = src_edges[violation_node_id]
    violation_edges.append(cur_src_edge[1])
    ignore_edges_of_func = None
    while True:
        cur_src_edge = src_edges[cur_src_edge[0]]
        # Do not add edges of intermediate functions.
        for data in cur_src_edge[1].getElementsByTagName('data'):
            if data.getAttribute('key') == 'returnFrom' and not ignore_edges_of_func:
                ignore_edges_of_func = data.firstChild.data
        if not ignore_edges_of_func:
            violation_edges.append(cur_src_edge[1])
        for data in cur_src_edge[1].getElementsByTagName('data'):
            if data.getAttribute('key') == 'enterFunction' and ignore_edges_of_func:
                if ignore_edges_of_func == data.firstChild.data:
                    ignore_edges_of_func = None
        if cur_src_edge[0] == entry_node_id:
            break

    # Two stages are required since for marking edges with warnings we need to know whether there
    # notes at violation path below.
    warn_edges = []
    for stage in ('notes', 'warns'):
        for edge in graph.getElementsByTagName('edge'):
            src_file, src_line, func_name = (None, None, None)

            for data in edge.getElementsByTagName('data'):
                if data.getAttribute('key') == 'originfile':
                    # Note, that not everything in trace should has a link to the sorce code!
                    # (for example, if assertion is specified in property automaton)
                    if data.firstChild:
                        src_file = data.firstChild.data
                elif data.getAttribute('key') == 'startline':
                    src_line = int(data.firstChild.data)
                elif data.getAttribute('key') == 'enterFunction':
                    func_name = data.firstChild.data

            if not src_file:
                src_file = default_src_file

            if src_file and src_line:
                if stage == 'notes' and src_file in notes and src_line in notes[src_file]:
                    logger.debug(
                        'Add note "{0}" from "{1}:{2}"'.format(notes[src_file][src_line], src_file,
                                                               src_line))
                    note = dom.createElement('data')
                    txt = dom.createTextNode(notes[src_file][src_line])
                    note.appendChild(txt)
                    note.setAttribute('key', 'note')
                    edge.appendChild(note)

                if stage == 'notes' and func_name and func_name in notes:
                    logger.debug(
                        'Add note "{0}" for call of model function "{1}" from "{2}"'.format(
                            notes[func_name], func_name, src_file))
                    note = dom.createElement('data')
                    txt = dom.createTextNode(notes[func_name])
                    note.appendChild(txt)
                    note.setAttribute('key', 'note')
                    edge.appendChild(note)

                if stage == 'warns' and src_file in warns and src_line in warns[src_file]:
                    # Add warning just if there are no more edges with notes at violation path
                    # below.
                    track_notes = False
                    note_found = False
                    for violation_edge in reversed(violation_edges):
                        if track_notes:
                            for data in violation_edge.getElementsByTagName('data'):
                                if data.getAttribute('key') == 'note':
                                    note_found = True
                                    break
                        if note_found:
                            break
                        if violation_edge == edge:
                            track_notes = True

                    if not note_found:
                        logger.debug(
                            'Add warning "{0}" from "{1}:{2}"'.format(warns[src_file][src_line],
                                                                      src_file, src_line))

                        warn = dom.createElement('data')
                        txt = dom.createTextNode(warns[src_file][src_line])
                        warn.appendChild(txt)
                        warn.setAttribute('key', 'warning')

                        # Add warning either to edge itself or to first edge that enters function
                        # and has note at violation path. If don't do the latter warning will be
                        # hidden by error trace visualizer.
                        warn_edge = edge
                        for cur_src_edge in violation_edges:
                            is_func_entry = False
                            for data in cur_src_edge.getElementsByTagName('data'):
                                if data.getAttribute('key') == 'enterFunction':
                                    is_func_entry = True
                            if is_func_entry:
                                for data in cur_src_edge.getElementsByTagName('data'):
                                    if data.getAttribute('key') == 'note':
                                        warn_edge = cur_src_edge

                        warn_edge.appendChild(warn)
                        warn_edges.append(warn_edge)

                        # Remove added warning to avoid its addition one more time.
                        del warns[src_file][src_line]

    # Remove notes from edges marked with warnings. Otherwise error trace visualizer will be
    # confused.
    for warn_edge in warn_edges:
        for data in warn_edge.getElementsByTagName('data'):
            if data.getAttribute('key') == 'note':
                warn_edge.removeChild(data)

    return graphml, src_files
