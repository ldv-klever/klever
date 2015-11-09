from Cloud.scheduler.requests import Session


class Server(Session):
    """Exchange with gateway via net."""

    def auth(self, user, password):
        """Using login and password try to proceed with authorization on the Verification Gateway server."""
        # TODO: Implement authorization at verification gateway.

    def register(self, scheduler_type, require_login=False):
        """
        Send unique ID to the Verification Gateway with the other properties to enable receiving tasks.
        :param scheduler_type: Scheduler scheduler_type.
        :param require_login: Flag indicating whether or not user should authorize to send tasks.
        """
        # TODO: Implement unique key generation

        # TODO: Implement registration of the scheduler at verification gateway

    def exchange_tasks(self, tasks):
        """
        Send to the verification gateway JSON set of solving/solved tasks and get new set back.

        :param tasks: String with JSON task set inside.
        :return: String with JSON task set received from the verification Gateway.
        """
        # TODO: Implement exchange of lists of tasks with verification gateway

        # TODO: Return new set of tasks
        return tasks

    def pull_task(self, identifier, description, archive):
        """
        Download verification task data from the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the description JSON file to save.
        :param archive: Path to the zip archive to save.
        """
        # TODO: Prepare directory with the description and for files

        # TODO: Receive JSON description and archive from the verification gateway and save them to the directory.

        # TODO: Unpack archive and remove it.

        # TODO: Return path to description and path to the sources

    def submit_solution(self, identifier, description, archive):
        """
        Send archive and description of an obtained from VerifierCloud solution to the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the JSON file to send.
        :param archive: Path to the zip archive to send.
        """
        # TODO: Send archive and JSON description to the verification gateway.

    def submit_nodes(self, nodes):
        """
        Send string with JSON description of nodes available for verification in VerifierCloud.
        :param nodes: String with JSON nodes description.
        """
        # TODO: Send JSON with node data to the verification gateway.

    def submit_tools(self, tools):
        """
        Send string with JSON description of verification tools available for verification in VerifierCloud.
        :param tools: String with JSON verification tools description.
        """
        # TODO: Send JSON with verifiers to the verification gateway.

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
