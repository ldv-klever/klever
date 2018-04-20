#
# Copyright (c) 2017 ISPRAS (http://www.ispras.ru)
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

import getpass
import json
import os
import re
import subprocess
import sys
import tarfile
import tempfile

from keystoneauth1.identity import v2
from keystoneauth1 import session
import glanceclient.client
import novaclient.client
import neutronclient.v2_0.client
import cinderclient.client

from kopenstack.instance import OSInstance
from kopenstack.ssh import SSH


class NotImplementedOSEntityAction(NotImplementedError):
    pass


class OSClients:
    def __init__(self, logger, session):
        self.logger = logger

        self.logger.info('Initialize OpenStack client for glance (images)')
        self.glance = glanceclient.client.Client('1', session=session)

        self.logger.info('Initialize OpenStack client for nova (instances)')
        self.nova = novaclient.client.Client('2', session=session)

        self.logger.info('Initialize OpenStack client for neutron (floating IPs)')
        self.neutron = neutronclient.v2_0.client.Client(session=session)

        self.logger.info('Initialize OpenStack client for cinder (volumes)')
        self.cinder = cinderclient.client.Client('2', session=session)


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
            'password': self._get_password(),
            'tenant_name': self.args.os_tenant_name
        })
        sess = session.Session(auth=auth)

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

    def _get_password(self):
        prompt = 'OpenStack password for authentication: '
        if sys.stdin.isatty():
            return getpass.getpass(prompt)
        else:
            self.logger.warning('Password will be echoed')
            print(prompt, end='', flush=True)
            return sys.stdin.readline().rstrip()

    def _show_instance(self, instance):
        return '{0} (status: {1}, IP: {2})'.format(instance.name, instance.status,
                                                   self._get_instance_floating_ip(instance))


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
                     floating_ip=instance.floating_ip) as ssh:
                ssh.sftp_put(os.path.join(os.path.dirname(__file__), os.path.pardir, 'bin', 'install-deps'),
                             'install-deps')
                ssh.execute_cmd('sudo ./install-deps')
                ssh.sftp.remove('install-deps')

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
            with SSH(args=self.args, logger=self.logger, name=self.name, floating_ip=self.instance.floating_ip) as ssh:
                self.logger.info('Copy and install init.d scripts')
                for dirpath, _, filenames in os.walk(os.path.join(os.path.dirname(__file__), os.path.pardir, 'init.d')):
                    for filename in filenames:
                        ssh.sftp_put(os.path.join(dirpath, filename),
                                     os.path.join(os.path.sep, 'etc', 'init.d', filename), dir=os.path.sep)
                        ssh.execute_cmd('sudo update-rc.d {0} defaults'.format(filename))

                self.logger.info(
                    'Copy scripts that can be used during creation/update of Klever developer instance')
                for script in ('configure-controller-and-schedulers', 'install-klever-bridge', 'prepare-environment'):
                    ssh.sftp_put(os.path.join(os.path.dirname(__file__), os.path.pardir, 'bin', script), script)

                self.logger.info('Prepare environment')
                ssh.execute_cmd('sudo ./prepare-environment')
                ssh.sftp.remove('prepare-environment')
                # Owner of these directories should be default user since later that user will put and update files
                # there.
                self.logger.info('Prepare configurations and programs directory')
                ssh.execute_cmd('mkdir -p klever-conf klever-programs')

                self._do_update(ssh)

                # Preserve instance if everything above went well.
                self.instance.keep_on_exit = True

    def _update_entity(self, name, instance_path, host_klever_conf, instance_klever_conf, ssh):
        if name not in host_klever_conf:
            raise KeyError('Entity "{0}" is not described'.format(name))

        host_desc = host_klever_conf[name]

        if 'version' not in host_desc:
            raise KeyError('Version is not specified for entity "{0}"'.format(name))

        host_version = host_desc['version']

        if 'path' not in host_desc:
            raise KeyError('Path is not specified for entity "{0}"'.format(name))

        host_path = host_desc['path'] if os.path.isabs(host_desc['path']) \
            else os.path.join(os.path.dirname(__file__), os.path.pardir, os.path.pardir, host_desc['path'])

        if not os.path.exists(host_path):
            raise ValueError('Path "{0}" does not exist'.format(host_path))

        is_git_repo = False

        # Use commit hash to uniquely identify entity version if it is provided as Git repository.
        if os.path.isdir(host_path) and os.path.isdir(os.path.join(host_path, '.git')):
            is_git_repo = True
            host_version = self._execute_cmd('git', '-C', host_path, 'rev-list', '-n', '1', host_version,
                                             get_output=True).rstrip()

        instance_version = instance_klever_conf[name]['version'] if name in instance_klever_conf else None

        if host_version == instance_version:
            self.logger.info('Entity "{0}" is up to date (version: "{1}")'.format(name, host_version))
            return False

        self.logger.info('Update "{0}" (host version: "{1}", instance version "{2}")'
                         .format(name, host_version, instance_version))

        instance_klever_conf[name] = {'version': host_version}
        for attr in ('name', 'executable path'):
            if attr in host_desc:
                instance_klever_conf[name][attr] = host_desc[attr]

        # Remove previous version of entity if so.
        if instance_version:
            ssh.execute_cmd('sudo rm -rf ' + instance_path)

        if is_git_repo:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_host_path = os.path.join(tmpdir, os.path.basename(os.path.realpath(host_path)))
                self._execute_cmd('git', 'clone', '-q', host_path, tmp_host_path)
                self._execute_cmd('git', '-C', tmp_host_path, 'checkout', '-q', host_version)
                # TODO: this makes imposible to detect Klever Core version.
                # shutil.rmtree(os.path.join(tmp_host_path, '.git'))
                ssh.sftp_put(tmp_host_path, instance_path)
        elif os.path.isfile(host_path) and tarfile.is_tarfile(host_path):
            instance_archive = os.path.basename(host_path)
            ssh.sftp.put(host_path, instance_archive)
            ssh.execute_cmd('mkdir -p "{0}"'.format(instance_path))
            ssh.execute_cmd('tar -C "{0}" -xf "{1}"'.format(instance_path, instance_archive))
            ssh.execute_cmd('rm -rf "{0}"'.format(instance_archive))
        elif os.path.isfile(host_path) or os.path.isdir(host_path):
            ssh.sftp_put(host_path, instance_path)
        else:
            raise NotImplementedError

        return True

    def _do_update(self, ssh):
        with open(self.args.klever_configuration_file) as fp:
            host_klever_conf = json.load(fp)

        if ssh.sftp_exist('klever.json'):
            with ssh.sftp.file('klever.json') as fp:
                instance_klever_conf = json.loads(fp.read().decode('utf8'))
        else:
            instance_klever_conf = {}

        is_update_klever = self._update_entity('Klever', 'klever', host_klever_conf, instance_klever_conf, ssh)

        is_update_controller_and_schedulers = False
        is_update_verification_backend = False
        if 'Klever Addons' in host_klever_conf:
            host_klever_addons_conf = host_klever_conf['Klever Addons']

            if 'Klever Addons' not in instance_klever_conf:
                instance_klever_conf['Klever Addons'] = {}

            instance_klever_addons_conf = instance_klever_conf['Klever Addons']

            for addon in host_klever_addons_conf.keys():
                if addon == 'Verification Backends':
                    if 'Verification Backends' not in instance_klever_addons_conf:
                        instance_klever_addons_conf['Verification Backends'] = {}

                    for verification_backend in host_klever_addons_conf['Verification Backends'].keys():
                        is_update_verification_backend |= \
                            self._update_entity(verification_backend, os.path.join('klever-addons',
                                                                                   'verification-backends',
                                                                                   verification_backend),
                                                host_klever_addons_conf['Verification Backends'],
                                                instance_klever_addons_conf['Verification Backends'],
                                                ssh)
                elif self._update_entity(addon, os.path.join('klever-addons', addon), host_klever_addons_conf,
                                         instance_klever_addons_conf, ssh) \
                        and addon in ('BenchExec', 'CIF', 'CIL', 'Consul', 'VerifierCloud Client'):
                    is_update_controller_and_schedulers = True

        if 'Programs' in host_klever_conf:
            host_programs_conf = host_klever_conf['Programs']

            if 'Programs' not in instance_klever_conf:
                instance_klever_conf['Programs'] = {}

            instance_programs_conf = instance_klever_conf['Programs']

            for program in host_programs_conf.keys():
                instance_path = os.path.join('klever-programs', program)
                if self._update_entity(program, instance_path, host_programs_conf, instance_programs_conf, ssh):
                    ssh.execute_cmd('sudo chown -LR klever:klever ' + instance_path)

        # TODO: if something below will fail below then one will see entities as successfully updated. But indeed this is a fatal error.
        self.logger.info('Specify actual versions of Klever, its addons and programs')
        with ssh.sftp.file('klever.json', 'w') as fp:
            json.dump(instance_klever_conf, fp, sort_keys=True, indent=4)

        if is_update_klever:
            self.logger.info('(Re)install and (re)start Klever Bridge')
            services = ('nginx', 'klever-bridge')
            ssh.execute_cmd('sudo sh -c "{0}"'.format(
                '; '.join('service {0} stop'.format(service) for service in services)
            ))
            ssh.execute_cmd('sudo ./install-klever-bridge')
            ssh.execute_cmd('sudo sh -c "{0}"'.format(
                '; '.join('service {0} start'.format(service) for service in services)
            ))

        if is_update_klever or is_update_controller_and_schedulers:
            self.logger.info('(Re)configure and (re)start Klever Controller and Klever schedulers')
            services = ('klever-controller', 'klever-native-scheduler', 'klever-verifiercloud-scheduler')
            ssh.execute_cmd('sudo sh -c "{0}"'.format(
                '; '.join('service {0} stop'.format(service) for service in services)
            ))
            ssh.execute_cmd('./configure-controller-and-schedulers')
            ssh.execute_cmd('sudo sh -c "{0}"'.format(
                '; '.join('service {0} start'.format(service) for service in services)
            ))

        if is_update_verification_backend and not is_update_klever and not is_update_controller_and_schedulers:
            self.logger.info('(Re)configure Klever Controller and Klever schedulers')
            # It is enough to reconfigure controller and schedulers since they automatically reread
            # configuration files holding changes of verification backends.
            ssh.execute_cmd('./configure-controller-and-schedulers')

    def update(self):
        with SSH(args=self.args, logger=self.logger, name=self.name,
                 floating_ip=self._get_instance_floating_ip(self._get_instance(self.name))) as ssh:
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
            self.logger.error('Floating IP {} is already in external network'.format(floating_ip_address))
            sys.exit(-1)
        elif not floating_ip and not share:
            self.logger.error('Floating IP {} is already in internal network'.format(floating_ip_address))
            sys.exit(-1)

        self.clients.neutron.update_floatingip(f_ip['id'], {"floatingip": {"port_id": None}})

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
                floating_ip = f_ip['floating_ip_address']
                break

        if not floating_ip:
            create_dict = {"floating_network_id": network_id}
            f_ip = self.clients.neutron.create_floatingip({"floatingip": create_dict})['floatingip']
            floating_ip = f_ip['floating_ip_address']

        port = self.clients.neutron.list_ports(device_id=instance.id)['ports'][0]
        update_dict = {'port_id': port['id']}
        self.clients.neutron.update_floatingip(f_ip['id'], {'floatingip': update_dict})

        self.logger.info('Floating IP {0} is attached to instance "{1}"'.format(floating_ip, self.name))

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
                # TODO: after this there won't be any base image for created Klever experimental instances.
                # Likely we need to overwrite corresponding attribute when creating these instances.
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
