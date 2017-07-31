#!/usr/bin/python3

from core.vtg.libraries.common import create_task, submit_task, wait_for_submitted_tasks, process_result
from core.vtg.strategies import Strategy


class SV(Strategy):
    long_name = "separated verification"
    name = "SV"

    def execute(self):
        verification_task, assertions = create_task(self)
        submitted_tasks = []
        for assertion in assertions:
            verification_task.assemble_task_files([assertion])
            verification_task.execute_cil()
            submitted_tasks.append(submit_task(verification_task, self))
        verification_result = wait_for_submitted_tasks(submitted_tasks, self)
        process_result(verification_result, self, verification_task)
