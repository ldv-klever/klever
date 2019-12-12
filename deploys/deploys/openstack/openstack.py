#
# Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
# Ivannikov Institute for System Programming of the Russian Academy of Sciences
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
from deploys.utils import get_password, install_entity, install_klever_addons, install_klever_build_bases, to_update


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

        self.clients = self.__connect()

    def __getattr__(self, name):
        self.logger.error('Action "{0}" is not supported for "{1}"'.format(name, self.kind))
        sys.exit(errno.ENOSYS)

    def _get_base_image(self, base_image_name):
        self.logger.info('Get base image matching "{0}"'.format(base_image_name))

        base_images = self._get_images(base_image_name)

        if len(base_images) == 0:
            self.logger.error('There are no base images matching "{0}"'.format(base_image_name))
            sys.exit(errno.EINVAL)

        if len(base_images) > 1:
            self.logger.error('There are several base images matching "{0}", please, resolve this conflict manually'
                              .format(base_image_name))
            sys.exit(errno.EINVAL)

        return base_images[0]

    def _get_images(self, image_name):
        images = []

        for image in self.clients.glance.images.list():
            if re.fullmatch(image_name, image.name):
                images.append(image)

        return images

    def __connect(self):
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
            self.logger.error(
                'There are several Klever base images matching "{0}", please, rename the appropriate ones manually'
                .format(klever_base_image_name))
            sys.exit(errno.EINVAL)

        if len(klever_base_images) == 1:
            i = 0
            # TODO: this does not work as expected as the only renaming is performed.
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
                        base_image=base_image, flavor_name='crawler.mini') as instance:
            with SSH(args=self.args, logger=self.logger, name=klever_base_image_name,
                     floating_ip=instance.floating_ip['floating_ip_address']) as ssh:
                self.logger.info('Create deployment directory')
                ssh.execute_cmd('mkdir klever-inst')
                with DeployConfAndScripts(self.logger, ssh, self.args.deployment_configuration_file,
                                          'creation of Klever base image'):
                    ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/install_deps.py --non-interactive')

            instance.create_image()

    def remove(self):
        klever_base_image_name = self.name if self.name else 'Klever Base'
        klever_base_images = self._get_images(klever_base_image_name)

        if len(klever_base_images) == 0:
            self.logger.error('There are no Klever base images matching "{0}"'.format(klever_base_image_name))
            sys.exit(errno.EINVAL)

        if len(klever_base_images) > 1:
            self.logger.error(
                'There are several Klever base images matching "{0}", please, remove the appropriate ones manually'
                .format(self.name))
            sys.exit(errno.EINVAL)

        self.clients.glance.images.delete(klever_base_images[0].id)


class OSKleverInstance(OSEntity):
    def __init__(self, args, logger):
        super().__init__(args, logger)

    def _install_or_update_deps(self, ssh):
        ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/install_deps.py --non-interactive' +
                        (' --update-packages' if self.args.update_packages else '') +
                        (' --update-python3-packages' if self.args.update_python3_packages else ''))

    def _create(self, is_dev):
        base_image = self._get_base_image(self.args.klever_base_image)

        klever_instances = self._get_instances(self.name)

        if klever_instances:
            self.logger.error('Klever instance(s) matching "{0}" already exists'.format(self.name))
            sys.exit(errno.EINVAL)

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
                                     sudo=True, directory=os.path.sep)
                        ssh.execute_cmd('sudo update-rc.d {0} defaults'.format(filename))

                with tempfile.NamedTemporaryFile('w', encoding='utf8') as fp:
                    # TODO: avoid using "/home/debian" - rename ssh username to instance username and add option to provide instance user home directory.
                    fp.write('KLEVER_DEPLOYMENT_DIRECTORY=/home/debian/klever-inst\n')
                    fp.write('KLEVER_DATA_DIR="/home/debian/klever-inst/klever/build bases"\n')
                    fp.flush()
                    ssh.sftp_put(fp.name, '/etc/default/klever', sudo=True, directory=os.path.sep)

                self.logger.info('Install systemd configuration files and services')
                ssh.execute_cmd('sudo mkdir -p /etc/conf.d')
                for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__), os.path.pardir,
                                                                  os.path.pardir, 'systemd', 'conf.d')):
                    for filename in filenames:
                        ssh.sftp_put(os.path.join(dirpath, filename), os.path.join('/etc/conf.d', filename),
                                     sudo=True, directory=os.path.sep)

                for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__), os.path.pardir,
                                                                  os.path.pardir, 'systemd', 'tmpfiles.d')):
                    for filename in filenames:
                        ssh.sftp_put(os.path.join(dirpath, filename), os.path.join('/etc/tmpfiles.d', filename),
                                     sudo=True, directory=os.path.sep)

                ssh.execute_cmd('sudo systemd-tmpfiles --create')

                for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__), os.path.pardir,
                                                                  os.path.pardir, 'systemd', 'system')):
                    for filename in filenames:
                        ssh.sftp_put(os.path.join(dirpath, filename), os.path.join('/etc/systemd/system', filename),
                                     sudo=True, directory=os.path.sep)

                with DeployConfAndScripts(self.logger, ssh, self.args.deployment_configuration_file,
                                          'creation of Klever instance'):
                    self._install_or_update_deps(ssh)
                    ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/prepare_env.py')
                    self._create_or_update(ssh, is_dev)

                # Preserve instance if everything above went well.
                self.instance.keep_on_exit = True

    def _create_or_update(self, ssh, is_dev):
        with open(self.args.deployment_configuration_file) as fp:
            deploy_conf = json.load(fp)

        # TODO: rename everywhere previous deployment information with deployment information since during deployment it is updated step by step.
        def get_prev_deploy_info():
            with ssh.sftp.file('klever-inst/klever.json') as nested_fp:
                return json.loads(nested_fp.read().decode('utf8'))

        prev_deploy_info = get_prev_deploy_info()

        def cmd_fn(*args):
            ssh.execute_cmd('sudo ' + ' '.join([shlex.quote(arg) for arg in args]))

        def install_fn(src, dst, allow_symlink=False, ignore=None):
            # To avoid warnings. This parameter is actually used in corresponding function in deploys/local/local.py.
            del allow_symlink
            self.logger.info('Install "{0}" to "{1}"'.format(src, dst))
            ssh.sftp_put(src, dst, ignore=ignore)

        def dump_cur_deploy_info(cur_deploy_info):
            with tempfile.NamedTemporaryFile('w', encoding='utf8') as nested_fp:
                json.dump(cur_deploy_info, nested_fp, sort_keys=True, indent=4)
                nested_fp.flush()
                ssh.execute_cmd('sudo rm klever-inst/klever.json')
                ssh.sftp_put(nested_fp.name, 'klever-inst/klever.json', sudo=True)

        if install_entity(self.logger, 'Klever', 'klever-inst/klever', deploy_conf, prev_deploy_info, cmd_fn,
                          install_fn):
            to_update(prev_deploy_info, 'Klever', dump_cur_deploy_info)

        install_klever_addons(self.logger, 'klever-inst', deploy_conf, prev_deploy_info, cmd_fn, install_fn,
                              dump_cur_deploy_info)
        install_klever_build_bases(self.logger, 'klever-inst/klever', deploy_conf, cmd_fn, install_fn)
        prev_deploy_info = get_prev_deploy_info()

        # Keeping entities to be updated in previous deployment information allows to properly deal when somethiing
        # went wrong above. For instance, script can update Klever but then fail when, say, installing programs. After
        # fixing issues with programs script will skip updating Klever and install them successfully. But also it will
        # perform actions required after updating Klever that happened at the first iteration since we remember that
        # Klever should be updated.
        if 'To update' in prev_deploy_info:
            if 'Klever' in prev_deploy_info['To update']:
                ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/install_klever_bridge.py{0}'
                                .format(' --development' if is_dev else ''))

            if 'Klever' in prev_deploy_info['To update'] or 'Controller & Schedulers' in prev_deploy_info['To update']:
                ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/configure_controller_and_schedulers.py{0}'
                                .format(' --development' if is_dev else ''))
            elif 'Verification Backends' in prev_deploy_info['To update']:
                ssh.execute_cmd('sudo PYTHONPATH=. ./deploys/configure_controller_and_schedulers.py'
                                ' --just-native-scheduler-task-worker')

            # Although we can forget to update entities step by step it is simpler and safer to forget about everything
            # at once. Indeed, there will be very rare failures above.
            del prev_deploy_info['To update']
            dump_cur_deploy_info(prev_deploy_info)

    def _get_instance(self, instance_name):
        self.logger.info('Get instance matching "{0}"'.format(instance_name))

        instances = self._get_instances(instance_name)

        if len(instances) == 0:
            self.logger.error('There are no intances matching "{0}"'.format(instance_name))
            sys.exit(errno.EINVAL)

        if len(instances) > 1:
            self.logger.error('There are several instances matching "{0}", please, resolve this conflict manually'
                              .format(instance_name))
            sys.exit(errno.EINVAL)

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
            self.logger.error('There are no floating IPs, please, resolve this manually')
            sys.exit(errno.EINVAL)

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

    def _update(self, instance, is_dev):
        with SSH(args=self.args, logger=self.logger, name=instance.name,
                 floating_ip=self._get_instance_floating_ip(instance)) as ssh:
            with DeployConfAndScripts(self.logger, ssh, self.args.deployment_configuration_file,
                                      'update of Klever instance'):
                self._install_or_update_deps(ssh)
                self._create_or_update(ssh, is_dev)


class OSKleverDeveloperInstance(OSKleverInstance):
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
        self._create(True)

    def update(self):
        self._update(self._get_instance(self.name), True)

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

        self.logger.error('OpenStack does not have network with "{}" name'.format(network_name))
        sys.exit(errno.EINVAL)


# TODO: Refactor this! This class shouldn't inherit OSKleverInstance as it corresponds to one or more OSKleverInstance. Because of this inheritance there is tricky mess of methods of this class and OSKleverInstance. Besides, refactoring is required for OSEntity (that indeed doesn't correspond to any single entity) and for OSKleverInstance as it also has some methods for dealing with many entities rather than a single instance.
class OSKleverExperimentalInstances(OSKleverInstance):
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
            self.logger.error('Please specify the number of new Klever experimental instances with help of' +
                              ' command-line option --instances')
            sys.exit(errno.EINVAL)

        klever_experimental_instances = self._get_instances(self.name_pattern)
        if klever_experimental_instances:
            self.logger.error('Klever experimental instances matching "{0}" already exist'.format(self.name_pattern))
            sys.exit(errno.EINVAL)

        # Often users will need to create a single Klever experimental instance, so, do that in a more optimal way.
        if self.args.instances == 1:
            self._create(False)
        else:
            self.logger.info(
                'Create master image "{0}" upon which Klever experimintal instances will be based'.format(self.name))
            master_image = None
            self.args.name = self.name
            # TODO: it would be better to detect shis automatically since it can change.
            # Use the same flavor for creating master instance as for creating Klever base image.
            flavor = self.args.flavor
            self.args.flavor = 'crawler.mini'
            try:
                self._create(False)
                self.args.flavor = flavor
                self.instance.create_image()
                master_image = self._get_base_image(self.name)

                instance_id = 1
                while instance_id <= self.args.instances:
                    instance_name = '{0}-{1}'.format(self.name, instance_id)
                    self.logger.info('Create Klever experimental instance "{0}"'.format(instance_name))

                    with OSInstance(logger=self.logger, clients=self.clients, args=self.args, name=instance_name,
                                    base_image=master_image, flavor_name=self.args.flavor, keep_on_exit=True):
                        pass

                    instance_id += 1
            # Always remove master instance and image if so. Klever experimental instances should be removed via
            # OSKleverExperimentalInstances#remove.
            finally:
                if self.instance:
                    self.instance.remove()
                if master_image:
                    self.logger.info('Remove master image "{0}"'.format(self.name))
                    # TODO: after this there won't be any base image for created Klever experimental instances. Likely we need to overwrite corresponding attribute when creating these instances.
                    self.clients.glance.images.delete(master_image.id)

    def update(self):
        klever_experimental_instances = self._get_instances(self.name_pattern)
        if not klever_experimental_instances:
            self.logger.error('There are no Klever experimental instances matching "{0}"'.format(self.name_pattern))
            sys.exit(errno.EINVAL)

        self.logger.warning('Please, do not keep Klever experimental instances for a long period of time'
                            ' (these updates are intended just for fixing initial deployment issues)')

        for klever_experimental_instance in klever_experimental_instances:
            self._update(klever_experimental_instance, False)

    def remove(self):
        klever_experimental_instances = self._get_instances(self.name_pattern)

        if len(klever_experimental_instances) == 0:
            self.logger.error('There are no Klever experimental instances matching "{0}"'.format(self.name_pattern))
            sys.exit(errno.EINVAL)

        for klever_experimental_instance in klever_experimental_instances:
            self.logger.info('Remove instance "{0}"'.format(klever_experimental_instance.name))
            self.clients.nova.servers.delete(klever_experimental_instance.id)
