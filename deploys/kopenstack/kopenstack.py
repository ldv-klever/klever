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
import logging
import json
import os
import re
import shutil
import subprocess
import tarfile
import tempfile
import time
import traceback

from keystoneauth1.identity import v2
from keystoneauth1 import session
import glanceclient.client
import novaclient.client
import neutronclient.v2_0.client
import cinderclient.client

from kopenstack.ssh import SSH


class NotImplementedOSEntityAction(NotImplementedError):
    pass


class OSEntity:
    def __init__(self, args):
        self.args = args

        self.kind = args.entity

        self.os_services = {}

    def __getattr__(self, name):
        raise NotImplementedOSEntityAction('You can not {0} "{1}"'.format(name, self.kind))

    def _connect(self, glance=False, nova=False, neutron=False, cinder=False):
        logging.info('Sign in to OpenStack')
        auth = v2.Password(**{
            'auth_url': self.args.os_auth_url,
            'username': self.args.os_username,
            'password': getpass.getpass('OpenStack password for authentication: '),
            'tenant_name': self.args.os_tenant_name
        })
        sess = session.Session(auth=auth)

        if glance:
            logging.info('Initialize OpenStack client for glance (images)')
            self.os_services['glance'] = glanceclient.client.Client('1', session=sess)

        if nova:
            logging.info('Initialize OpenStack client for nova (instances)')
            self.os_services['nova'] = novaclient.client.Client('2', session=sess)

        if neutron:
            logging.info('Initialize OpenStack client for neutron (floating IPs)')
            self.os_services['neutron'] = neutronclient.v2_0.client.Client(session=sess)

        if cinder:
            logging.info('Initialize OpenStack client for cinder (volumes)')
            self.os_services['cinder'] = cinderclient.client.Client('2', session=sess)

    def _execute_cmd(self, *args, get_output=False):
        logging.info('Execute command "{0}"'.format(' '.join(args)))
        if get_output:
            return subprocess.check_output(args).decode('utf8')
        else:
            subprocess.check_call(args)

    def _get_base_image(self, base_image_name):
        logging.info('Get base image matching "{0}"'.format(base_image_name))

        base_images = self._get_images(base_image_name)

        if len(base_images) == 0:
            raise ValueError('There are no base images matching "{0}"'.format(base_image_name))

        if len(base_images) > 1:
            raise ValueError('There are several base images matching "{0}", please, resolve this conflict manually'
                             .format(base_image_name))

        return base_images[0]

    def _get_images(self, image_name):
        images = []

        for image in self.os_services['glance'].images.list():
            if re.fullmatch(image_name, image.name):
                images.append(image)

        return images

    def _get_instance(self, instance_name):
        logging.info('Get instance matching "{0}"'.format(instance_name))

        instances = self._get_instances(instance_name)

        if len(instances) == 0:
            raise ValueError('There are no intances matching "{0}"'.format(instance_name))

        if len(instances) > 1:
            raise ValueError('There are several instances matching "{0}", please, resolve this conflict manually'
                             .format(instance_name))

        return instances[0]

    def _get_instance_floating_ip(self, instance):
        logging.info('Get instance floating IP')

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

        for instance in self.os_services['nova'].servers.list():
            if re.fullmatch(instance_name, instance.name):
                instances.append(instance)

        return instances

    def _sftp_put(self, ssh, sftp, host_path, instance_path, dir=None):
        # Always transfer files using compressed tar archives to preserve file permissions and reduce net load.
        with tempfile.NamedTemporaryFile(suffix='.tar.gz') as fp:
            instance_archive = os.path.basename(fp.name)
            with tarfile.open(fileobj=fp, mode='w:gz') as TarFile:
                TarFile.add(host_path, instance_path)
            fp.flush()
            fp.seek(0)
            sftp.putfo(fp, instance_archive)

        # Use sudo to allow extracting archives outside home directory.
        ssh.execute_cmd('{0} -xf {1}'.format('sudo tar -C ' + dir if dir else 'tar', instance_archive))
        ssh.execute_cmd('rm ' + instance_archive)


class OSKleverBaseImage(OSEntity):
    def __init__(self, args):
        super().__init__(args)

    def show(self):
        self._connect(glance=True)

        klever_base_image_name = self.name if self.name else 'Klever Base.*'
        klever_base_images = self._get_images(klever_base_image_name)

        if len(klever_base_images) == 1:
            logging.info('There is Klever base image "{0}" (status: {1}) matching "{2}"'
                         .format(klever_base_images[0].name, klever_base_images[0].status, klever_base_image_name))
        elif len(klever_base_images) > 1:
            logging.info('There are {0} Klever base images matching "{1}":\n* {2}'
                         .format(len(klever_base_images), klever_base_image_name,
                                 '\n* '.join(['"{0}" (status: {1})'.format(image.name, image.status)
                                              for image in klever_base_images])))
        else:
            logging.info('There are no Klever base images matching "{0}"'.format(klever_base_image_name))

    def create(self):
        self._connect(glance=True, nova=True, neutron=True)

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
                    logging.info('Rename previous Klever base image to "{0}"'.format(deprecated_klever_base_image_name))
                    self.os_services['glance'].images.update(klever_base_images[0].id,
                                                             name=deprecated_klever_base_image_name)
                    break

        with OSInstance(os_services=self.os_services, name=klever_base_image_name, base_image=base_image,
                        flavor_name='keystone.xlarge') as instance:
            with SSH(args=self.args, name=klever_base_image_name, floating_ip=instance.floating_ip) as ssh:
                script = os.path.join(os.path.dirname(__file__), os.path.pardir, 'bin', 'install-deps')

                sftp = ssh.ssh.open_sftp()

                try:
                    sftp.put(script, os.path.basename(script))
                finally:
                    sftp.close()

                ssh.execute_cmd('sudo ./install-deps')

            instance.create_image()

    def remove(self):
        self._connect(glance=True)

        klever_base_image_name = self.name if self.name else 'Klever Base'
        klever_base_images = self._get_images(klever_base_image_name)

        if len(klever_base_images) == 0:
            raise ValueError('There are no Klever base images matching "{0}"'.format(klever_base_image_name))

        if len(klever_base_images) > 1:
            raise ValueError(
                'There are several Klever base images matching "{0}", please, remove the appropriate ones manually'
                .format(self.name))

        self.os_services['glance'].images.delete(klever_base_images[0].id)


class OSKleverDeveloperInstance(OSEntity):
    def __init__(self, args):
        super().__init__(args)

        self.name = self.args.name or '{0}-klever-dev'.format(self.args.os_username)

    def show(self):
        self._connect(nova=True)

        klever_developer_instances = self._get_instances(self.name)

        if len(klever_developer_instances) == 1:
            logging.info('There is Klever developer instance "{0}" matching "{1}"'
                         .format('{0} (status: {1})'
                                 .format(klever_developer_instances[0].name, klever_developer_instances[0].status),
                                 self.name))
        elif len(klever_developer_instances) > 1:
            logging.info('There are {0} Klever developer instances matching "{1}":\n* {2}'
                         .format(len(klever_developer_instances), self.name,
                                 '\n* '.join(['{0} (status: {1})'.format(instance.name, instance.status)
                                              for instance in klever_developer_instances])))
        else:
            logging.info('There are no Klever developer instances matching "{0}"'.format(self.name))

    def create(self):
        self._connect(glance=True, nova=True, neutron=True)

        base_image = self._get_base_image(self.args.klever_base_image)

        klever_developer_instances = self._get_instances(self.name)

        if klever_developer_instances:
            raise ValueError('Klever developer instance matching "{0}" already exists'.format(self.name))

        with OSInstance(os_services=self.os_services, name=self.name, base_image=base_image,
                        flavor_name=self.args.flavor, keep_on_exit=True) as instance:
            with SSH(args=self.args, name=self.name, floating_ip=instance.floating_ip) as ssh:
                sftp = ssh.ssh.open_sftp()

                try:
                    # Copy and install all init.d scripts.
                    for dirpath, dirnames, filenames in os.walk(os.path.join(os.path.dirname(__file__), os.path.pardir,
                                                                             'init.d')):
                        for filename in filenames:
                            self._sftp_put(ssh, sftp, os.path.join(dirpath, filename),
                                           os.path.join(os.path.sep, 'etc', 'init.d', filename), dir=os.path.sep)
                            ssh.execute_cmd('sudo update-rc.d {0} defaults'.format(filename))

                    logging.info('Copy scripts that can be used during creation/update of Klever developer instance')
                    for script in ('configure-controller-and-schedulers', 'install-klever-bridge', 'prepare-environment'):
                        self._sftp_put(ssh, sftp,
                                       os.path.join(os.path.dirname(__file__), os.path.pardir, 'bin', script), script)

                    # Prepare environment once when new Klever developer instance is created.
                    ssh.execute_cmd('sudo sh -c "./prepare-environment; sudo chown -R $(id -u):$(id -g) klever-conf klever-work"')
                    sftp.remove('prepare-environment')

                    # TODO: initialize volumes

                    # TODO: like for update
                    with sftp.file('klever.json', mode='w') as fp:
                        json.dump({}, fp)
                finally:
                    sftp.close()

    def _update_entity(self, name, host_klever_conf, instance_klever_conf, ssh, sftp):
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

        instance_version = instance_klever_conf.get(name)

        if host_version == instance_version:
            logging.info('Entity "{0}" is up to date (version: "{1}")'.format(name, host_version))
            return False

        logging.info('Update "{0}" (host version: "{1}", instance version "{2}")'
                     .format(name, host_version, instance_version))

        instance_klever_conf[name] = host_version

        if name == 'Klever':
            instance_path = 'klever'
        else:
            instance_path = os.path.join('klever-addons', name)

        # Remove previous version of entity if so.
        if instance_version:
            ssh.execute_cmd('rm -rf ' + instance_path)

        if is_git_repo:
            with tempfile.TemporaryDirectory() as tmpdir:
                self._execute_cmd('git', 'clone', '-q', host_path, tmpdir)
                self._execute_cmd('git', '-C', tmpdir, 'checkout', '-q', host_version)
                shutil.rmtree(os.path.join(tmpdir, '.git'))
                host_path = tmpdir
                self._sftp_put(ssh, sftp, host_path, instance_path)
        elif os.path.isfile(host_path) or os.path.isdir(host_path):
            self._sftp_put(ssh, sftp, host_path, instance_path)
        else:
            raise NotImplementedError

        return True

    def update(self):
        self._connect(nova=True)

        with open(self.args.klever_configuration_file) as fp:
            host_klever_conf = json.load(fp)

        instance = self._get_instance(self.name)

        with SSH(args=self.args, name=self.name, floating_ip=self._get_instance_floating_ip(instance)) as ssh:
            sftp = ssh.ssh.open_sftp()

            try:
                with sftp.file('klever.json') as fp:
                    instance_klever_conf = json.load(fp)

                if self._update_entity('Klever', host_klever_conf, instance_klever_conf, ssh, sftp):
                    # TODO: ditto for schedulers.
                    ssh.execute_cmd('sudo sh -c "service nginx stop; service klever-bridge stop; ./install-klever-bridge; service klever-bridge start; service nginx start"')

                if 'Addons' in host_klever_conf:
                    if 'Addons' not in instance_klever_conf:
                        instance_klever_conf['Addons'] = {}

                    for addon_name in host_klever_conf['Addons'].keys():
                        if addon_name == 'Verification Backends':
                            if 'Verification Backends' not in instance_klever_conf['Addons']:
                                instance_klever_conf['Addons']['Verification Backends'] = {}

                            is_update_verification_backend = False
                            for verification_backend in host_klever_conf['Addons']['Verification Backends'].keys():
                                is_update_verification_backend |= \
                                    self._update_entity(verification_backend,
                                                        host_klever_conf['Addons']['Verification Backends'],
                                                        instance_klever_conf['Addons']['Verification Backends'],
                                                        ssh, sftp)

                            if is_update_verification_backend:
                                # It is enough to reconfigure controller and schedulers since they automatically reread
                                # configuration files holding changes of verification backends.
                                ssh.execute_cmd('./configure-controller-and-schedulers')
                        else:
                            # TODO: stop, configure, start schedulers if BenchExec, CIF, CIL or Consul changes.
                            self._update_entity(addon_name, host_klever_conf['Addons'], instance_klever_conf['Addons'],
                                                ssh, sftp)

                # Specify actual versions of Klever and its addons.
                with sftp.file('klever.json', 'w') as fp:
                    json.dump(instance_klever_conf, fp, sort_keys=True, indent=4)

                # TODO: copy sources.
            finally:
                sftp.close()

    def remove(self):
        self._connect(nova=True)
        self.os_services['nova'].servers.delete(self._get_instance(self.name).id)

    def ssh(self):
        self._connect(nova=True)

        with SSH(args=self.args, name=self.name,
                 floating_ip=self._get_instance_floating_ip(self._get_instance(self.name))) as ssh:
            ssh.open_shell()


class OSKleverExperimentalInstances(OSEntity):
    def __init__(self, args):
        super().__init__(args)

        self.name = self.args.name or '{0}-klever-experiment'.format(self.args.os_username)

    def show(self):
        self._connect(nova=True)

        klever_experimental_instances = self._get_instances(self.name + '.*')

        if len(klever_experimental_instances) == 1:
            logging.info('There is Klever experimental instance "{0}" matching "{1}"'
                         .format(klever_experimental_instances[0].name, self.name))
        elif len(klever_experimental_instances) > 1:
            logging.info('There are {0} Klever experimental instances matching "{1}":\n* {2}'
                         .format(len(klever_experimental_instances), self.name,
                                 '\n* '.join([instance.name for instance in klever_experimental_instances])))
        else:
            logging.info('There are no Klever experimental instances matching "{0}"'.format(self.name))

    def create(self):
        # TODO: like for Klever developer instance create.
        pass

    def remove(self):
        self._connect(nova=True)
        self.os_services['nova'].servers.delete(self._get_instance(self.name).id)

    def ssh(self):
        self._connect(nova=True)

        with SSH(args=self.args, name=self.name,
                 floating_ip=self._get_instance_floating_ip(self._get_instance(self.name))) as ssh:
            ssh.open_shell()


class OSInstanceCreationTimeout(RuntimeError):
    pass


class OSInstance:
    CREATION_ATTEMPTS = 5
    CREATION_TIMEOUT = 120
    CREATION_CHECK_INTERVAL = 5
    CREATION_RECOVERY_INTERVAL = 10
    OPERATING_SYSTEM_STARTUP_DELAY = 15
    IMAGE_CREATION_ATTEMPTS = 3
    IMAGE_CREATION_TIMEOUT = 300
    IMAGE_CREATION_CHECK_INTERVAL = 10
    IMAGE_CREATION_RECOVERY_INTERVAL = 30

    def __init__(self, os_services, name, base_image, flavor_name, keep_on_exit=False):
        self.os_services = os_services
        self.name = name
        self.base_image = base_image
        self.flavor_name = flavor_name
        self.keep_on_exit = keep_on_exit

    def __enter__(self):
        logging.info('Create instance "{0}" of flavor "{1}" on the base of image "{2}"'
                     .format(self.name, self.flavor_name, self.base_image.name))

        instance = None
        flavor = self.os_services['nova'].flavors.find(name=self.flavor_name)
        attempts = self.CREATION_ATTEMPTS

        while attempts > 0:
            try:
                instance = self.os_services['nova'].servers.create(name=self.name, image=self.base_image, flavor=flavor,
                                                                   key_name='ldv')

                timeout = self.CREATION_TIMEOUT

                while timeout > 0:
                    if instance.status == 'ACTIVE':
                        for floating_ip in self.os_services['neutron'].list_floatingips()['floatingips']:
                            if floating_ip['status'] == 'DOWN':
                                self.floating_ip = floating_ip['floating_ip_address']
                                break
                        if not self.floating_ip:
                            raise RuntimeError('There are no free floating IPs, please, resolve this manually')
                        instance.add_floating_ip(self.floating_ip)
                        logging.info('Instance "{0}" with floating IP {1} is running'
                                     .format(self.name, self.floating_ip))
                        self.instance = instance

                        logging.info(
                            'Wait for {0} seconds until operating system will start before performing other operations'
                            .format(self.OPERATING_SYSTEM_STARTUP_DELAY))
                        time.sleep(self.OPERATING_SYSTEM_STARTUP_DELAY)

                        return self
                    else:
                        timeout -= self.CREATION_CHECK_INTERVAL
                        logging.info('Wait for {0} seconds until instance will run ({1})'
                                     .format(self.CREATION_CHECK_INTERVAL,
                                             'remaining timeout is {0} seconds'.format(timeout)))
                        time.sleep(self.CREATION_CHECK_INTERVAL)
                        instance = self.os_services['nova'].servers.get(instance.id)

                raise OSInstanceCreationTimeout
            except Exception as e:
                if instance:
                    instance.delete()
                attempts -= 1
                logging.warning(
                    'Could not create instance, wait for {0} seconds and try {1} times more{2}'
                    .format(self.CREATION_RECOVERY_INTERVAL, attempts,
                            '' if isinstance(e, OSInstanceCreationTimeout) else '\n' + traceback.format_exc().rstrip()))
                time.sleep(self.CREATION_RECOVERY_INTERVAL)

        raise RuntimeError('Could not create instance')

    def __exit__(self, etype, value, traceback):
        if not self.keep_on_exit and self.instance:
            logging.info('Terminate instance "{0}"'.format(self.name))
            self.instance.delete()

    def create_image(self):
        logging.info('Create image "{0}"'.format(self.name))

        attempts = self.IMAGE_CREATION_ATTEMPTS

        while attempts > 0:
            try:
                image_id = self.instance.create_image(image_name=self.name)

                timeout = self.IMAGE_CREATION_TIMEOUT

                while timeout > 0:
                    image = self.os_services['glance'].images.get(image_id)

                    if image.status == 'active':
                        logging.info('Image "{0}" was created'.format(self.name))
                        return
                    else:
                        timeout -= self.IMAGE_CREATION_CHECK_INTERVAL
                        logging.info('Wait for {0} seconds until image will be created ({1})'
                                     .format(self.IMAGE_CREATION_CHECK_INTERVAL,
                                             'remaining timeout is {0} seconds'.format(timeout)))
                        time.sleep(self.IMAGE_CREATION_CHECK_INTERVAL)

                raise OSInstanceCreationTimeout
            except Exception as e:
                attempts -= 1
                logging.warning(
                    'Could not create image, wait for {0} seconds and try {1} times more{2}'
                    .format(self.CREATION_RECOVERY_INTERVAL, attempts,
                            '' if isinstance(e, OSInstanceCreationTimeout) else '\n' + traceback.format_exc().rstrip()))
                time.sleep(self.IMAGE_CREATION_RECOVERY_INTERVAL)

        raise RuntimeError('Could not create image')


def execute_os_entity_action(args):
    logging.info('{0} {1}'.format(args.action.capitalize(), args.entity))

    if args.entity == 'Klever base image':
        getattr(OSKleverBaseImage(args), args.action)()
    elif args.entity == 'Klever developer instance':
        getattr(OSKleverDeveloperInstance(args), args.action)()
    elif args.entity == 'Klever experimental instances':
        getattr(OSKleverExperimentalInstances(args), args.action)()
    else:
        raise NotImplementedError('Entity "{0}" is not supported'.format(args.entity))
