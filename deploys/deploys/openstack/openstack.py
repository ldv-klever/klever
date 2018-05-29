#
# Copyright (c) 2017-2018 ISPRAS (http://www.ispras.ru)
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

import errno
import json
import os
import re
import shlex
import subprocess
import sys
import tempfile

from keystoneauth1.identity import v2
from keystoneauth1 import session
import glanceclient.client
import keystoneauth1.exceptions
import novaclient.client
import novaclient.exceptions
import neutronclient.v2_0.client
import cinderclient.client

from deploys.openstack.instance import OSInstance
from deploys.openstack.ssh import SSH
from deploys.utils import get_password, install_extra_dep_or_program, install_extra_deps, install_programs


class NotImplementedOSEntityAction(NotImplementedError):
    pass


class OSClients:
    def __init__(self, logger, sess):
        self.logger = logger

        self.logger.info('Initialize OpenStack clients')

        self.glance = glanceclient.client.Client('1', session=sess)
        self.nova = novaclient.client.Client('2', session=sess)
        self.neutron = neutronclient.v2_0.client.Client(session=sess)
        self.cinder = cinderclient.client.Client('2', session=sess)


class OSEntity:
    def __init__(self, args, logger):
        self.args = args
        self.logger = logger

        self.kind = args.entity

        self.clients = self._connect()

    def __getattr__(self, name):
        raise NotImplementedOSEntityAction('You can not {0} "{1}"'.format(name, self.kind))

    def _connect(self):
        self.logger.info('Sign in to OpenStack')
        auth = v2.Password(**{
            'auth_url': self.args.os_auth_url,
            'username': self.args.os_username,
            'password': get_password(self.logger, 'OpenStack password for authentication: '),
            'tenant_name': self.args.os_tenant_name
        })
        sess = session.Session(auth=auth)

        try:
            # Perform a request to OpenStack in order to check the correctness of provided username and password.
            sess.get_auth_headers()
        except keystoneauth1.exceptions.http.Unauthorized:
            self.logger.error('Sign in failed: invalid username or password')
            sys.exit(errno.EACCES)

        return OSClients(self.logger, sess)

    def _execute_cmd(self, *args, get_output=False):
        self.logger.info('Execute command "{0}"'.format(' '.join(args)))
        if get_output:
            return subprocess.check_output(args).decode('utf8')
        else:
            subprocess.check_call(args)

    def _get_base_image(self, base_image_name):
        self.logger.info('Get base image matching "{0}"'.format(base_image_name))

        base_images = self._get_images(base_image_name)

        if len(base_images) == 0:
            raise ValueError('There are no base images matching "{0}"'.format(base_image_name))

        if len(base_images) > 1:
            raise ValueError('There are several base images matching "{0}", please, resolve this conflict manually'
                             .format(base_image_name))

        return base_images[0]

    def _get_images(self, image_name):
        images = []

        for image in self.clients.glance.images.list():
            if re.fullmatch(image_name, image.name):
                images.append(image)

        return images

    def _get_instance(self, instance_name):
        self.logger.info('Get instance matching "{0}"'.format(instance_name))

        instances = self._get_instances(instance_name)

        if len(instances) == 0:
            raise ValueError('There are no intances matching "{0}"'.format(instance_name))

        if len(instances) > 1:
            raise ValueError('There are several instances matching "{0}", please, resolve this conflict manually'
                             .format(instance_name))

        return instances[0]

    def _get_instance_floating_ip(self, instance):
        self.logger.info('Get instance floating IP')

        floating_ip = None
        for network_addresses in instance.addresses.values():
            for address in network_addresses:
                if address.get('OS-EXT-IPS:type') == 'floating':
                    floating_ip = address.get('addr')
                    break
            if floating_ip:
                break

        if not floating_ip:
            raise ValueError('There are no floating IPs, please, resolve this manually')

        return floating_ip

    def _get_instances(self, instance_name):
        instances = []

        for instance in self.clients.nova.servers.list():
            if re.fullmatch(instance_name, instance.name):
                instances.append(instance)

        return instances

    def _show_instance(self, instance):
        return '{0} (status: {1}, IP: {2})'.format(instance.name, instance.status,
                                                   self._get_instance_floating_ip(instance))


class DeployConfAndScripts:
    def __init__(self, logger, ssh, deploy_conf_file, action):
        self.logger = logger
        self.ssh = ssh
        self.deploy_conf_file = deploy_conf_file
        self.action = action

    def __enter__(self):
        self.logger.info('Copy deployment configuration file')
        self.ssh.sftp_put(self.deploy_conf_file, 'klever.json')

        self.logger.info('Copy scripts that can be used during {0}'.format(self.action))
        self.ssh.sftp_put(os.path.dirname(os.path.dirname(__file__)), 'deploys')

    def __exit__(self, etype, value, traceback):
        self.logger.info('Remove scripts used during {0}'.format(self.action))
        self.ssh.execute_cmd('rm -r deploys')

        self.logger.info('Remove deployment configuration file')
        self.ssh.sftp.remove('klever.json')


class OSKleverBaseImage(OSEntity):
    def __init__(self, args, logger):
        super().__init__(args, logger)

        self.name = self.args.name

    def show(self):
        klever_base_image_name = self.name if self.name else 'Klever Base.*'
        klever_base_images = self._get_images(klever_base_image_name)

        if len(klever_base_images) == 1:
            self.logger.info('There is Klever base image "{0}" (status: {1}) matching "{2}"'
                             .format(klever_base_images[0].name, klever_base_images[0].status, klever_base_image_name))
        elif len(klever_base_images) > 1:
            self.logger.info('There are {0} Klever base images matching "{1}":\n* {2}'
                             .format(len(klever_base_images), klever_base_image_name,
                                     '\n* '.join(['"{0}" (status: {1})'.format(image.name, image.status)
                                                 for image in klever_base_images])))
        else:
            self.logger.info('There are no Klever base images matching "{0}"'.format(klever_base_image_name))

    def create(self):
        klever_base_image_name = self.name if self.name else 'Klever Base'
        klever_base_images = self._get_images(klever_base_image_name)
        base_image = self._get_base_image(self.args.base_image)

        if len(klever_base_images) > 1:
            raise ValueError(
                'There are several Klever base images matching "{0}", please, rename the appropriate ones manually'
                .format(klever_base_image_name))

        if len(klever_base_images) == 1:
            i = 0
            while True:
                deprecated_klever_base_image_name = klever_base_image_name + \
                    ' (deprecated{0})'.format(' ' + str(i) if i else '')
                deprecated_klever_base_images = self._get_images(deprecated_klever_base_image_name)

                if deprecated_klever_base_images:
                    i += 1
                else:
                    self.logger.info('Rename previous Klever base image to "{0}"'
                                     .format(deprecated_klever_base_image_name))
                    self.clients.glance.images.update(klever_base_images[0].id, name=deprecated_klever_base_image_name)
                    break

        with OSInstance(logger=self.logger, clients=self.clients, args=self.args, name=klever_base_image_name,
                        base_image=base_image, flavor_name='keystone.xlarge') as instance:
            with SSH(args=self.args, logger=self.logger, name=klever_base_image_name,
                     floating_ip=instance.floating_ip['floating_ip_address']) as ssh:
                with DeployConfAndScripts(self.logger, ssh, self.args.deployment_configuration_file,
                                          'creation of Klever base image'):
                    self.logger.info('Create deployment directory')
                    os.makedirs('klever-inst')
                    ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/install_deps.py --non-interactive')

            instance.create_image()

    def remove(self):
        klever_base_image_name = self.name if self.name else 'Klever Base'
        klever_base_images = self._get_images(klever_base_image_name)

        if len(klever_base_images) == 0:
            raise ValueError('There are no Klever base images matching "{0}"'.format(klever_base_image_name))

        if len(klever_base_images) > 1:
            raise ValueError(
                'There are several Klever base images matching "{0}", please, remove the appropriate ones manually'
                .format(self.name))

        self.clients.glance.images.delete(klever_base_images[0].id)


class OSKleverDeveloperInstance(OSEntity):
    def __init__(self, args, logger):
        super().__init__(args, logger)

        self.name = self.args.name or '{0}-klever-dev'.format(self.args.os_username)

        # For external users like OSKleverExperimentalInstances#create.
        self.instance = None

    def show(self):
        klever_developer_instances = self._get_instances(self.name)

        if len(klever_developer_instances) == 1:
            self.logger.info('There is Klever developer instance "{0}" matching "{1}"'
                             .format(self._show_instance(klever_developer_instances[0]), self.name))
        elif len(klever_developer_instances) > 1:
            self.logger.info('There are {0} Klever developer instances matching "{1}":\n* {2}'
                             .format(len(klever_developer_instances), self.name,
                                     '\n* '.join([self._show_instance(instance)
                                                 for instance in klever_developer_instances])))
        else:
            self.logger.info('There are no Klever developer instances matching "{0}"'.format(self.name))

    def create(self):
        base_image = self._get_base_image(self.args.klever_base_image)

        klever_developer_instances = self._get_instances(self.name)

        if klever_developer_instances:
            raise ValueError('Klever developer instance matching "{0}" already exists'.format(self.name))

        with OSInstance(logger=self.logger, clients=self.clients, args=self.args, name=self.name,
                        base_image=base_image, flavor_name=self.args.flavor) as self.instance:
            with SSH(args=self.args, logger=self.logger, name=self.name,
                     floating_ip=self.instance.floating_ip['floating_ip_address']) as ssh:
                # TODO: looks like deploys/local/local.py too much.
                self.logger.info('Install init.d scripts')
                for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__), os.path.pardir,
                                                                  os.path.pardir, 'init.d')):
                    # TODO: putting files one by one is extremely slow.
                    for filename in filenames:
                        ssh.sftp_put(os.path.join(dirpath, filename), os.path.join('/etc/init.d', filename),
                                     sudo=True, dir=os.path.sep)
                        ssh.execute_cmd('sudo update-rc.d {0} defaults'.format(filename))

                with tempfile.NamedTemporaryFile('w', encoding='utf8') as fp:
                    # TODO: avoid using "/home/debian" - rename ssh username to instance username and add option to provide instance user home directory.
                    fp.write('KLEVER_DEPLOYMENT_DIRECTORY=/home/debian/klever-inst\nKLEVER_USERNAME=klever\n')
                    fp.flush()
                    ssh.sftp_put(fp.name, '/etc/default/klever', sudo=True, dir=os.path.sep)

                with DeployConfAndScripts(self.logger, ssh, self.args.deployment_configuration_file,
                                          'creation of Klever developer instance'):
                    ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/prepare_env.py --mode OpenStack --username klever')
                    self._do_update(ssh, deps=False)

                # Preserve instance if everything above went well.
                self.instance.keep_on_exit = True

    def _do_update(self, ssh, deps=True):
        with open(self.args.deployment_configuration_file) as fp:
            deploy_conf = json.load(fp)

        is_update = {
            'Klever': False,
            'Controller & Schedulers': False,
            'Verification Backends': False
        }

        if deps:
            ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/install_deps.py --non-interactive' +
                            (' --update-packages' if self.args.update_packages else '') +
                            (' --update-python3-packages' if self.args.update_python3_packages else ''))

        with ssh.sftp.file('klever-inst/klever.json') as fp:
            prev_deploy_info = json.loads(fp.read().decode('utf8'))

        def cmd_fn(*args):
            # First argument is logger that is already known in "ssh".
            ssh.execute_cmd('sudo ' + ' '.join([shlex.quote(arg) for arg in args[1:]]))

        def install_fn(logger, src, dst):
            logger.info('Install "{0}" to "{1}"'.format(src, dst))
            ssh.sftp_put(src, dst, sudo=True)

        is_update['Klever'] = install_extra_dep_or_program(self.logger, 'Klever', 'klever-inst/klever', deploy_conf,
                                                           prev_deploy_info, cmd_fn, install_fn)

        def dump_cur_deploy_info():
            with tempfile.NamedTemporaryFile('w', encoding='utf8') as fp:
                json.dump(prev_deploy_info, fp, sort_keys=True, indent=4)
                fp.flush()
                ssh.execute_cmd('sudo rm klever-inst/klever.json')
                ssh.sftp_put(fp.name, 'klever-inst/klever.json', sudo=True)

        if is_update['Klever']:
            dump_cur_deploy_info()

        try:
            is_update['Controller & Schedulers'], is_update['Verification Backends'] = \
                install_extra_deps(self.logger, 'klever-inst', deploy_conf, prev_deploy_info, cmd_fn, install_fn)
        # Without this we won't store information on successfully installed/updated extra dependencies and following
        # installation/update will fail.
        finally:
            if is_update['Controller & Schedulers'] or is_update['Verification Backends']:
                dump_cur_deploy_info()

        is_update_programs = False
        try:
            is_update_programs = install_programs(self.logger, 'klever', 'klever-inst', deploy_conf, prev_deploy_info,
                                                  cmd_fn, install_fn)
        # Like above.
        finally:
            if is_update_programs:
                dump_cur_deploy_info()

        if is_update['Klever']:
            ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/install_klever_bridge.py --action {0} --mode OpenStack'
                            .format(self.args.action))

        cmd = 'sudo PYTHONPATH=. ./deploys/configure_controller_and_schedulers.py --mode OpenStack'
        if is_update['Klever'] or is_update['Controller & Schedulers']:
            ssh.execute_cmd(cmd)

        if is_update['Verification Backends'] and not is_update['Klever'] and not is_update['Controller & Schedulers']:
            ssh.execute_cmd(cmd + ' --just-native-scheduler-task-worker')

    def update(self):
        with SSH(args=self.args, logger=self.logger, name=self.name,
                 floating_ip=self._get_instance_floating_ip(self._get_instance(self.name))) as ssh:
            with DeployConfAndScripts(self.logger, ssh, self.args.deployment_configuration_file,
                                      'update of Klever developer instance'):
                self._do_update(ssh)

    def remove(self):
        # TODO: wait for successfull deletion everywhere.
        self.clients.nova.servers.delete(self._get_instance(self.name).id)

    def ssh(self):
        with SSH(args=self.args, logger=self.logger, name=self.name,
                 floating_ip=self._get_instance_floating_ip(self._get_instance(self.name)), open_sftp=False) as ssh:
            ssh.open_shell()

    def share(self):
        instance = self._get_instance(self.name)
        self._remove_floating_ip(instance, share=True)
        self._assign_floating_ip(instance, share=True)

    def hide(self):
        instance = self._get_instance(self.name)
        self._remove_floating_ip(instance, share=False)
        self._assign_floating_ip(instance, share=False)

    def _remove_floating_ip(self, instance, share=False):
        if share:
            network_name = OSInstance.NETWORK_TYPE["internal"]
        else:
            network_name = OSInstance.NETWORK_TYPE["external"]

        floating_ip = None
        network_id = self._get_network_id(network_name)

        floating_ip_address = self._get_instance_floating_ip(instance)

        for f_ip in self.clients.neutron.list_floatingips()['floatingips']:
            if f_ip['floating_ip_address'] == floating_ip_address and f_ip['floating_network_id'] == network_id:
                floating_ip = f_ip
                break

        if not floating_ip and share:
            self.logger.info('Floating IP {} is already in external network'.format(floating_ip_address))
            sys.exit()
        elif not floating_ip and not share:
            self.logger.info('Floating IP {} is already in internal network'.format(floating_ip_address))
            sys.exit()

        self.clients.neutron.update_floatingip(floating_ip['id'], {"floatingip": {"port_id": None}})

        self.logger.info('Floating IP {0} is dettached from instance "{1}"'.format(floating_ip_address, self.name))

    def _assign_floating_ip(self, instance, share=False):
        if share:
            network_name = OSInstance.NETWORK_TYPE["external"]
        else:
            network_name = OSInstance.NETWORK_TYPE["internal"]

        floating_ip = None
        network_id = self._get_network_id(network_name)

        for f_ip in self.clients.neutron.list_floatingips()['floatingips']:
            if f_ip['status'] == 'DOWN' and f_ip['floating_network_id'] == network_id:
                floating_ip = f_ip
                break

        if not floating_ip:
            floating_ip = self.clients.neutron.create_floatingip(
                {"floatingip": {"floating_network_id": network_id}}
            )['floatingip']

        port = self.clients.neutron.list_ports(device_id=instance.id)['ports'][0]
        self.clients.neutron.update_floatingip(floating_ip['id'], {'floatingip': {'port_id': port['id']}})

        self.logger.info('Floating IP {0} is attached to instance "{1}"'
                         .format(floating_ip['floating_ip_address'], self.name))

    def _get_network_id(self, network_name):
        for net in self.clients.neutron.list_networks()['networks']:
            if net['name'] == network_name:
                return net['id']

        raise ValueError('OpenStack does not have network with "{}" name'.format(network_name))


class OSKleverExperimentalInstances(OSEntity):
    def __init__(self, args, logger):
        super().__init__(args, logger)

        self.name = self.args.name or '{0}-klever-experiment'.format(self.args.os_username)

        # It is assumed that all requested Klever experimental instances have the same unique prefix (name).
        self.name_pattern = self.name + '.*'

    def show(self):
        klever_experimental_instances = self._get_instances(self.name_pattern)

        if len(klever_experimental_instances) == 1:
            self.logger.info('There is Klever experimental instance "{0}" matching "{1}"'
                             .format(self._show_instance(klever_experimental_instances[0]), self.name_pattern))
        elif len(klever_experimental_instances) > 1:
            self.logger.info('There are {0} Klever experimental instances matching "{1}":\n* {2}'
                             .format(len(klever_experimental_instances), self.name_pattern,
                                     '\n* '.join([self._show_instance(instance)
                                                  for instance in klever_experimental_instances])))
        else:
            self.logger.info('There are no Klever experimental instances matching "{0}"'.format(self.name_pattern))

    def create(self):
        if not self.args.instances:
            raise ValueError('Please specify the number of new Klever experimental instances with help of' +
                             ' command-line option --instances')

        self.logger.info(
            'Create master image "{0}" upon which Klever experimintal instances will be based'.format(self.name))
        master_instance = None
        master_image = None
        self.args.name = self.name
        # Use the same flavor for creating master instance as for creating Klever base image.
        flavor = self.args.flavor
        self.args.flavor = 'keystone.xlarge'
        try:
            klever_developer_instance = OSKleverDeveloperInstance(self.args, self.logger)
            klever_developer_instance.create()
            master_instance = klever_developer_instance.instance
            self.args.flavor = flavor
            master_instance.create_image()
            master_image = self._get_base_image(self.name)

            instance_id = 1
            while instance_id <= self.args.instances:
                instance_name = '{0}-{1}'.format(self.name, instance_id)
                self.logger.info('Create Klever experimental instance "{0}"'.format(instance_name))

                with OSInstance(logger=self.logger, clients=self.clients, args=self.args, name=instance_name,
                                base_image=master_image, flavor_name=self.args.flavor, keep_on_exit=True):
                    pass

                instance_id += 1
        # Always remove master instance in case of failures. Klever experimental instances should be removed via
        # OSKleverExperimentalInstances#remove.
        finally:
            if master_instance:
                master_instance.remove()
            if master_image:
                self.logger.info('Remove master image "{0}"'.format(self.name))
                # TODO: after this there won't be any base image for created Klever experimental instances. Likely we need to overwrite corresponding attribute when creating these instances.
                self.clients.glance.images.delete(master_image.id)

    def remove(self):
        klever_experimental_instances = self._get_instances(self.name_pattern)

        if len(klever_experimental_instances) == 0:
            raise ValueError('There are no Klever experimental instances matching "{0}"'.format(self.name_pattern))

        for klever_experimental_instance in klever_experimental_instances:
            self.logger.info('Remove instance "{0}"'.format(klever_experimental_instance.name))
            self.clients.nova.servers.delete(klever_experimental_instance.id)

    def ssh(self):
        with SSH(args=self.args, logger=self.logger, name=self.name,
                 floating_ip=self._get_instance_floating_ip(self._get_instance(self.name))) as ssh:
            ssh.open_shell()


def execute_os_entity_action(args, logger):
    logger.info('{0} {1}'.format(args.action.capitalize(), args.entity))

    if args.entity == 'Klever base image':
        getattr(OSKleverBaseImage(args, logger), args.action)()
    elif args.entity == 'Klever developer instance':
        getattr(OSKleverDeveloperInstance(args, logger), args.action)()
    elif args.entity == 'Klever experimental instances':
        getattr(OSKleverExperimentalInstances(args, logger), args.action)()
    else:
        raise NotImplementedError('Entity "{0}" is not supported'.format(args.entity))
