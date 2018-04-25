#
# Copyright (c) 2014-2016 ISPRAS (http://www.ispras.ru)
# Institute for System Programming of the Russian Academy of Sciences
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
#

import concurrent.futures 
import json 
import logging
import os 

import schedulers as schedulers 
import utils 


class Scheduler(schedulers.SchedulerExchange):
    #hamster CHECK: пока делаю только для native
	"""
    Implement the scheduler which is used to run tasks and jobs on cluster.
    Parent class SchedulerExchange in _init_
    """
    #hamster TODO: надо добавлять по ходу написания программы сюда self переменные


    @staticmethod
    def scheduler_type():
        """Return type of the scheduler: 'VerifierCloud', 'Klever'."""
        return "Klever"

    def __init__(self, conf, work_dir):
        """
        Do scheduler specific initialization
        """
        
        super(Scheduler, self).__init__(conf, work_dir)

        #hamster TODO: надо добавлять по ходу написания программы сюда инициализацию self переменных
        

        self.init_scheduler()


    def init_scheduler(self):
        """
        Initialize scheduler completely.
        This method should be called both at constructing stage and scheduler reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """

        super(Scheduler, self).init_scheduler()


        def _init_k8s_cluster(self, k8s_init_config=None):
            '''
            Initialize kubernetes cluster.
            :param k8s_init_config: Part of self.conf. Dictionary with initialization information like version, configuration for master in k8s and etc.
            This method should be called both at constructing stage and scheduler reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
            '''
            '''
            #hamster TODO:
                on master:
                    0) Check all component of kubernetes is installed
                        if not, installed it
                    1) Make config file for master
                    2) Initialize master
                on node:
                    0) Check all component of kubernetes is installed
                        if not, installed it
                    1) Make config file for node
                    2) Initialize node and connect it to master
            '''
                
                def k8s_installation(config):
                    """
                    Just install kubernetes components
                    :return: Error if happened. Otherwise None.
                    """
                    commands = (
                        'sudo apt install curl',
                        'curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo apt-key add',
                        'sudo add-apt-repository "deb [arch=amd64] https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable"',
                        'sudo apt-get update',
                        'echo Y | sudo apt-get install docker-ce',
                        'apt-cache madison docker-ce',
                        'sudo curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add',
                        "echo 'deb http://apt.kubernetes.io/ kubernetes-xenial main' | sudo tee /etc/apt/sources.list.d/kubernetes.list",
                        'sudo apt-get update',
                        'sudo apt-get install -y kubelet kubectl kubeadm kubernetes-cni'
                        )
                    for line in commands:
                        error = __execute_cmd(line, give_output=True)[1]
                        if error:
                            return error
                    return None

            # Loading default installation configuration if necessary 
            if not k8s_init_config:
                temp_config = _get_k8s_init_config()
            else:
                #hamster TODO: need to add check, that is dictionary
                temp_config = k8s_init_config

            # Check that necessary components install and available
            if not (self._check_k8s_component_version("kubeadm") and
                    self._check_k8s_component_version("kubelet") and
                    self._check_k8s_component_version("kubectl") and
                    self._check_k8s_component_version("kubernetes-cni"))
                k8s_installation(temp_config)

            def make_master_conf_file(conf):
                """
                Made configuration kubernetes file for master initialization in working directory.
                
                :param conf: Master configuration from dictionary.
                :return: File (path).
                """
                with open("master_config.yaml", "w") as conf_file: 
                    str_1 = "apiVersion: kubeadm.k8s.io/v1alpha1"
                    conf_file.write(str_1)
                    str_2 = "kind: MasterConfiguration"
                    conf_file.write(str_2)
                    if "advertiseAddress" or "bindPort" in conf:
                        str_3 = "api:"
                        conf_file.write(str_3)
                        if "advertiseAddress" in conf:
                            str_4 = "  advertiseAddress: " + conf["advertiseAddress"] 
                            conf_file.write(str_4)
                        else:
                            str_5 = "  bindPort: " + conf["bindPort"] 
                            conf_file.write(str_5)
                    if "token" in conf:
                        str_6 = "token: " + conf["token"]
                        conf_file.write(str_6)
                    if "tokenTTL" in conf:
                        str_7 = "tokenTTL: " + conf["tokenTTL"]
                        conf_file.write(str_7)
                    return "master_config.yaml"
            

            if "master configuration" in temp_config:
                file_name = make_master_conf_file(k8s_init_config["master configuration"])
                master_conf = os.path.join(self.work_dir, file_name)
                cmd_string = 'sudo kubeadm init --config "' + master_conf + '"'
                __execute_cmd(cmd_string)#hamster TODO: add check error from command 
            else:
                __execute_cmd("sudo kubeadm init")#hamster TODO: add check error from command



        _init_k8s_cluster()

        _init_consul()

        _init_native_sheduler()

    def _init_consul(self):
        '''
        Initialize and adjust consul to cluster.
        This method should be called both at constructing stage and scheduler reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        '''


    def _init_native_sheduler(self):
        """
        Initialize native scheduler options that we needed. #hamster TODO: перефразировать, так как звучит плохо и скорее всего потом будет значить тоже другое.
        This method should be called both at constructing stage and scheduler reinitialization. Thus, all object attribute should be cleaned up and set as it is a newly created object.
        """

    def schedule(self, pending_tasks, pending_jobs):


        return


    def prepare_task(self, identifier, description):

    def prepare_job(self, identifier, configuration):

    def solve_task(self, identifier, description, user, password):

    def solve_job(self, identifier, configuration):

    def flush(self):

    def process_task_result(self, identifier, future):

    def process_job_result(self, identifier, future):

    def cancel_job(self, identifier, future):

    def cancel_task(self, identifier, future):

    def terminate(self):

    def update_nodes(self, wait_controller=False):

    def update_tools(self):    

# ---------------------
# Some utility methods:

    def output_changer(self, output):
    """
    Change temporary strange output into list of lines.
    
    :param output: Output that need to be in correct form. Now is (list of lines, list of lines)
    :return new_output: Return output like list of lines.
    """
    
    new_output = output[0]
    for line in output[1]:
        new_output.append(line)
    return new_output
    

    #hamster TODO: method to execute chosen commands in shell
    def __execute_cmd(args, shell=True, cwd=None, timeout=2, give_output=False):
        """
        Execute given command in a separate process catching its stderr if necessary.

        :param args: Command arguments.
        :param cwd: Current working directory to run the command.
        :param timeout: Timeout for the command.
        ?:return: subprocess.Popen.returncode.
        """

        # Change working directory, if need
        init_path = os.getcwd()
        changed_path = False
        if cwd and os.path.isdir(cwd):
            if os.path.isabs(cwd):
                os.chdir(cwd)
            else:
                temp_path = os.path.join(init_path, cwd)
                os.chdir(cwd)
            changed_path = True

        original_sigint_handler = signal.getsignal(signal.SIGINT)
        original_sigtrm_handler = signal.getsignal(signal.SIGTERM)
        
        def restore_handlers():
            signal.signal(signal.SIGTERM, original_sigtrm_handler)
            signal.signal(signal.SIGINT, original_sigint_handler)

        # Check: process is alive
        def process_alive(pid):
            try:
                os.kill(pid, 0) 
            except OSError:
                return False
            else:
                return True

        def handler(arg1, arg2):
            def terminate():
                print("{}: Cancellation of {} is successfull, exiting".format(os.getpid(), pid))
                os._exit(-1)

            # Kill if not dead
            if proc and proc.pid: 
                pid = proc.pid
                print("{}: Cancelling process {}".format(os.getpid(), pid))
                # Sent initial signals
                try:
                    os.kill(pid, signal.SIGINT)
                except ProcessLookupError:
                    terminate(pid)
                restore_handlers() 

                try:
                    # Try to wait - it helps if a process is waiting for something, we need to check its status
                    proc.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    print('{}: Process {} is still alive ...'.format(os.getpid(), pid))
                    # Lets try it again
                    try:
                        os.killpg(os.getpgid(pid), signal.SIGTERM)
                        os.killpg(os.getpgid(pid), signal.SIGINT)
                        os.kill(pid, signal.SIGKILL)
                    except ProcessLookupError:
                        terminate(pid)
                    # It should not survive after kill, lets wait a couple of seconds
                    time.sleep(10)

            terminate()

        def set_handlers():
            signal.signal(signal.SIGTERM, handler)
            signal.signal(signal.SIGINT, handler)

        def output_stream(proc, name, str_pipe, _print=False):
        """
        Function to write output and error from command (subprocess).
        
        :param name: Name of the output stream.
        :param str_pipe: Pipe or file descriptor from which write.
        :param _print: Temporary print flag. #hamster TODO: Need to delete and change code after debug and input logger in code.
        """
            print("{} :\n".format(name))
            
            temp_queue = StreamQueue(str_pipe, name, True)
            temp_queue.start()
            
            output = []
            first_try = True # If cmd doesn't have output
            last_line = "not empty"
            last_try = True
            while not temp_queue.finished or last_try:
                if temp_queue.traceback:
                    raise RuntimeError(
                        '{0} reader thread failed with the following traceback:\n{1}'.format(name, temp_queue.traceback))
                last_try = not temp_queue.finished
                # if not last_try:
                if last_line:
                    time.sleep(timeout)
                elif first_try:
                    first_try = False
                    time.sleep(timeout)
                else:
                    os.kill(proc.pid, signal.SIGINT)
                    restore_handlers()
                    raise RuntimeError(
                        'Command freezed:\n"{}"\n'.format(args))
                line = ""
                while True:
                    last_line = line
                    line = temp_queue.get()
                    if line is None:
                        break
                    if give_output:
                        output.append(line)
                    if _print:
                        print(line)

            temp_queue.join() 

            if give_output:
                return output
            else:
                return None



        #hamster TODO: Delete flag and that part of code after debug and logger import
        temp_flag = False
        if "hamster_print_flag" in globals():
            temp_flag = hamster_print_flag

        set_handlers() 
        proc = subprocess.Popen(args, stderr=subprocess.PIPE, stdout=subprocess.PIPE, shell=shell)

        if give_output:
            return_output = output_stream(proc, "STDOUT", proc.stdout, temp_flag)
        else:
            output_stream(proc, "STDOUT", proc.stderr, temp_flag)

        if give_output:
            return_error = output_stream(proc, "STDERR", proc.stderr, temp_flag)
        else:
            output_stream(proc, "STDERR", proc.stdout, temp_flag)

        proc.wait()
        restore_handlers()

        # Return working directory, if was changed
        if changed_path:
            os.chdir(init_path)

        if give_output:
            return tulpe(return_output, return_error)
        else:
            return proc.returncode


    def _check_k8s_component_version(component_k8s):
    """
    Check version of the given component which cluster will use
    
    :param component_k8s: Name string of the component from list: 'kubeadm', 'kubectl', 'kubelet', 'kubernetes-cni' #hamster CHECK: don't forget to check, that you wrote out all needed component
    :return: Version <string> or None.
    """

    if not component_k8s:
        raise RuntimeError('component_k8s')#hamster TODO: write correct error code : error if component_k8s don't given
    elif component_k8s == 'kubeadm':
        temp_return = __execute_cmd("kubeadm version", timeout=5, give_output=True)
        for line in temp_return[0]:
            find_version = re.search(r'GitVersion:"v.*"', line)
            if find_version:
                kubeadm_version = re.search(r'GitVersion:"v.*"', line).group(0).split(',')[0]
                return kubeadm_version # Smth like: GitVersion:"v1.10.1"
        return None
    elif component_k8s == 'kubectl':
        temp_return = __execute_cmd("kubectl version", timeout=5, give_output=True)
        for line in temp_return[0]:
            find_version = re.search(r'GitVersion:"v.*"', line)
            if find_version:
                kubectl_version = re.search(r'GitVersion:"v.*"', line).group(0).split(',')[0]
                return kubectl_version
        return None
    else:
        raise RuntimeError('component_k8s')#hamster TODO: write correct error code : error wrong value in param



    #hamster CHECK:
    # Temporary methods 
    @staticmethod
    def _get_k8s_init_config():
        config_init_k8s = {
            #hamster TODO: insert needed parameters
        }
        '''
        possible parameters:
        version of kubernetes (for installation)


        '''
        return config_init_k8s


#hamster CHECK: function from utils, delete after write custom execute method
def execute(args, env=None, cwd=None, timeout=None, logger=None, stderr=sys.stderr, stdout=sys.stdout,
        disk_limitation=None, disk_checking_period=30):
    """
    Execute given command in a separate process catching its stderr if necessary.

    :param args: Command erguments.
    :param env: Environment variables.
    :param cwd: Current working directory to run the command.
    :param timeout: Timeout for the command.
    :param logger: Logger object.
    :param stderr: Pipe or file descriptor to redirect output. Use it if logger is not provided.
    :param stdout: Pipe or file descriptor to redirect output. Use it if logger is not provided.
    :param disk_limitation: Allowed integer size of disk memory in Bytes of current working directory.
    :param disk_checking_period: Integer number of seconds for the disk space measuring interval.
    :return: subprocess.Popen.returncode.
    """

    original_sigint_handler = signal.getsignal(signal.SIGINT)
    original_sigtrm_handler = signal.getsignal(signal.SIGTERM) 

    def restore_handlers():
        signal.signal(signal.SIGTERM, original_sigtrm_handler)
        signal.signal(signal.SIGINT, original_sigint_handler)
    
    def process_alive(pid):
        try:
            os.kill(pid, 0)
        except OSError:
            return False
        else:
            return True
            
    def handler(arg1, arg2):
        def terminate():
            print("{}: Cancellation of {} is successfull, exiting".format(os.getpid(), pid))
            os._exit(-1)

        # Kill if not dead
        if p and p.pid: 
            pid = p.pid
            print("{}: Cancelling process {}".format(os.getpid(), pid))
            # Sent initial signals
            try:
                os.kill(pid, signal.SIGINT)
            except ProcessLookupError:
                terminate()
            restore_handlers() 

            try:
                # Try to wait - it helps if a process is waiting for something, we need to check its status
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                print('{}: Process {} is still alive ...'.format(os.getpid(), pid))
                # Lets try it again
                try:
                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                    os.killpg(os.getpgid(pid), signal.SIGINT)
                    os.kill(pid, signal.SIGKILL)
                except ProcessLookupError:
                    terminate()
                # It should not survive after kill, lets wait a couple of seconds
                time.sleep(10)

        terminate()

    def set_handlers():
        signal.signal(signal.SIGTERM, handler)
        signal.signal(signal.SIGINT, handler)

    def disk_controller(pid, limitation, period):
        while process_alive(pid):
            s = dir_size("./")
            if s > limitation:
                # Kill the process
                print("Reached disk memory limit of {}B, killing process {}".format(limitation, pid))
                os.kill(pid, signal.SIGINT) 
            time.sleep(period)
        os._exit(0)

    def activate_disk_limitation(pid, limitation):
        if limitation:
            checker = multiprocessing.Process(target=disk_controller, args=(pid, limitation, disk_checking_period))
            checker.start()
            return checker
        else:
            return None

    set_handlers() 
    cmd = args[0] 
    if logger:
        logger.debug('Execute:\n{0}{1}{2}'.format(cmd,
                                                  '' if len(args) == 1 else ' ',
                                                  ' '.join('"{0}"'.format(arg) for arg in args[1:])))

        logger.debug('Execute:\n{0}{1}{2}'.format(cmd,
                                                  '' if len(args) == 1 else ' ',
                                                  ' '.join('"{0}"'.format(arg) for arg in args[1:])))
        p = subprocess.Popen(args, env=env, stderr=subprocess.PIPE, cwd=cwd, preexec_fn=os.setsid)
        disk_checker = activate_disk_limitation(p.pid, disk_limitation)
        err_q = StreamQueue(p.stderr, 'STDERR', True)
        err_q.start()

        # Print to logs everything that is printed to STDOUT and STDERR each timeout seconds. Last try is required to
        # print last messages queued before command finishes.
        last_try = True
        while not err_q.finished or last_try:
            if err_q.traceback: 
                raise RuntimeError(
                    'STDERR reader thread failed with the following traceback:\n{0}'.format(err_q.traceback))
            last_try = not err_q.finished
            time.sleep(timeout if isinstance(timeout, int) else 0)
            
            output = []
            while True:
                line = err_q.get()
                if line is None:
                    break
                output.append(line)
            if output: 
                m = '"{0}" outputted to {1}:\n{2}'.format(cmd, err_q.stream_name, '\n'.join(output))
                logger.warning(m)

        err_q.join() 
    else:
        p = subprocess.Popen(args, env=env, cwd=cwd, preexec_fn=os.setsid, stderr=stderr, stdout=stdout)
        disk_checker = activate_disk_limitation(p.pid, disk_limitation)

    p.wait()
    if disk_checker: 
        disk_checker.terminate() 
        disk_checker.join()
    restore_handlers()

    # Check dir size after a stop
    if disk_limitation: 
        size = dir_size("./")
        if size >= disk_limitation:
            raise RuntimeError("Disk space limitation of {}B is exceeded".format(disk_limitation))

    return p.returncode 

__author__ = 'Ilja Zakharov <ilja.zakharov@ispras.ru>'