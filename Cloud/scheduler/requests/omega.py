import requests
import time
import logging
import Cloud.scheduler.requests as requests
import Cloud.utils.omega as omega


class Server(requests.Server):
    """Exchange with gateway via net."""

    session = None

    def register(self, scheduler_type):
        """
        Send unique ID to the Verification Gateway with the other properties to enable receiving tasks.
        :param scheduler_type: Scheduler scheduler_type.
        :param require_login: Flag indicating whether or not user should authorize to send tasks.
        """
        # Create session
        self.session = omega.Session(self.conf["name"], self.conf["user"], self.conf["password"], scheduler_type)

    def exchange(self, tasks):
        """
        Send to the verification gateway JSON set of solving/solved tasks and get new set back.

        :param tasks: String with JSON task set inside.
        :return: String with JSON task set received from the verification Gateway.
        """
        data = {"jobs and tasks status": tasks}
        return self.session.json_exchange("get_jobs_and_tasks/", data)

    def pull_task(self, identifier, description, archive):
        """
        Download verification task data from the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the description JSON file to save.
        :param archive: Path to the zip archive to save.
        """
        pass


    def submit_solution(self, identifier, description, archive):
        """
        Send archive and description of an obtained from VerifierCloud solution to the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the JSON file to send.
        :param archive: Path to the zip archive to send.
        """
        pass

    def submit_nodes(self, nodes):
        """
        Send string with JSON description of nodes available for verification in VerifierCloud.
        :param nodes: String with JSON nodes description.
        """
        pass

    def submit_tools(self, tools):
        """
        Send string with JSON description of verification tools available for verification in VerifierCloud.
        :param tools: String with JSON verification tools description.
        """
        pass

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
