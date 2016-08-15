import json

import server as server
import utils.bridge as bridge


class Server(server.AbstractServer):
    """Exchange with gateway via net."""

    session = None

    def register(self, scheduler_type=None):
        """
        Send unique ID to the Verification Gateway with the other properties to enable receiving tasks.
        :param scheduler_type: Scheduler scheduler_type.
        :param require_login: Flag indicating whether or not user should authorize to send tasks.
        """
        # Create session
        if scheduler_type:
            data = {"scheduler": scheduler_type}
        else:
            data = {}
        self.session = bridge.Session(self.conf["name"], self.conf["user"], self.conf["password"], data)

    def exchange(self, tasks):
        """
        Send to the verification gateway JSON set of solving/solved tasks and get new set back.

        :param tasks: String with JSON task set inside.
        :return: String with JSON task set received from the verification Gateway.
        """
        data = {"jobs and tasks status": json.dumps(tasks, ensure_ascii=False, sort_keys=True, indent=4)}
        ret = self.session.json_exchange("service/get_jobs_and_tasks/", data)
        return json.loads(ret["jobs and tasks status"])

    def pull_task(self, identifier, archive):
        """
        Download verification task data from the verification gateway.

        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to save.
        """
        self.session.get_archive("service/download_task/", {"task id": identifier}, archive)


    def submit_solution(self, identifier, description, archive):
        """
        Send archive and description of an obtained from VerifierCloud solution to the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the JSON file to send.
        :param archive: Path to the zip archive to send.
        """
        self.session.push_archive("service/upload_solution/",
                                  {
                                      "task id": identifier,
                                      "description": json.dumps(description, ensure_ascii=False, sort_keys=True,
                                                                indent=4)
                                  },
                                  archive)

    def submit_nodes(self, nodes):
        """
        Send string with JSON description of nodes available for verification in VerifierCloud.
        :param nodes: String with JSON nodes description.
        """
        data = {"nodes data": json.dumps(nodes, ensure_ascii=False, sort_keys=True, indent=4)}
        self.session.json_exchange("service/update_nodes/", data)

    def submit_tools(self, tools):
        """
        Send string with JSON description of verification tools available for verification in VerifierCloud.
        :param tools: String with JSON verification tools description.
        """
        pass

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
