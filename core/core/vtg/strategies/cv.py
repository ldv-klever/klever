#!/usr/bin/python3

from core.vtg.libraries.common import create_task, submit_task, wait_for_submitted_tasks, process_result
from core.vtg.strategies import Strategy


class CV(Strategy):
    long_name = "combined verification"
    name = "CV"

    def execute(self):
        verification_task, assertions = create_task(self)
        verification_task.assemble_task_files(assertions)
        verification_task.execute_cil()
        submitted_task = submit_task(verification_task, self)
        verification_result = wait_for_submitted_tasks([submitted_task], self)
        process_result(verification_result, self, verification_task)
