import abc
import uuid


class Session(metaclass=abc.ABCMeta):
    """Start exchange with verification gate."""

    def __init__(self, conf, work_dir):
        """
        Save relevant configuration, authorize at remote verification
        gateway and register there as scheduler.
        :param conf: Dictionary with relevant configuration.
        :param work_dir: PAth to the working directory.
        :return:
        """
        self.conf = conf
        self.work_dir = work_dir
        self._key = str(uuid.uuid4())

    @abc.abstractmethod
    def auth(self, user, password):
        """
        Using login and password try to proceed with authorization on the Verification Gateway server.
        :param user: Scheduler user user.
        :param password: Scheduler user password
        :return:
        """
        return

    @abc.abstractmethod
    def register(self, scheduler_type):
        """
        Send unique ID to the Verification Gateway with the other properties to enable receiving tasks.
        :param scheduler_type: Scheduler type.
        """
        return

    @abc.abstractmethod
    def exchange_tasks(self, tasks):
        """
        Send to the verification gateway JSON set of solving/solved tasks and get new set back.

        :param tasks: String with JSON task set inside.
        :return: String with JSON task set received from the verification Gateway.
        """
        return tasks

    @abc.abstractmethod
    def pull_task(self, identifier, archive):
        """
        Download verification task data from the verification gateway.
        :param identifier: Verification task identifier.
        :param archive: Path to the zip archive to save.
        """
        return

    @abc.abstractmethod
    def submit_solution(self, identifier, description, archive):
        """
        Send archive and description of an obtained from VerifierCloud solution to the verification gateway.

        :param identifier: Verification task identifier.
        :param description: Path to the JSON file to send.
        :param archive: Path to the zip archive to send.
        """
        return

    @abc.abstractmethod
    def submit_nodes(self, nodes):
        """
        Send string with JSON description of nodes available for verification in VerifierCloud.
        :param nodes: String with JSON nodes description.
        """
        return

    @abc.abstractmethod
    def submit_tools(self, tools):
        """
        Send string with JSON description of verification tools available for verification in VerifierCloud.
        :param tools: String with JSON verification tools description.
        """
        return


__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'
