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

import os
import time
from datetime import datetime

from django.conf import settings
from django.db.models.base import ModelBase

from bridge.utils import BridgeException
from tools.models import LockTable, CallLogs

# Waiting while other function try to lock with DB table + try to lock with DB table
# So maximum waiting time is (MAX_WAITING * 2) in seconds.
if settings.UNLOCK_FAILED_REQUESTS:
    MAX_WAITING = 30
else:
    MAX_WAITING = 300


class ExecLocker:
    lockfile = os.path.join(settings.BASE_DIR, 'media', '.lock')

    def __init__(self, groups):
        self.names = self.__get_affected_models(groups)
        self.lock_ids = set()
        # wait1 and wait2
        self.waiting_time = [0, 0]

    def lock(self):
        if len(self.names) == 0:
            return
        # Lock with file while we locking with DB table
        while True:
            try:
                with open(self.lockfile, mode='x'):
                    break
            except FileExistsError:
                time.sleep(0.1)
                self.waiting_time[0] += 0.1
                if self.waiting_time[0] > MAX_WAITING:
                    if settings.UNLOCK_FAILED_REQUESTS:
                        try:
                            os.remove(self.lockfile)
                        except FileNotFoundError:
                            pass
                    else:
                        raise RuntimeError('Not enough time to lock execution of view')

        try:
            self.__lock_names()
        finally:
            try:
                os.remove(self.lockfile)
            except FileNotFoundError:
                pass

    def unlock(self):
        if len(self.lock_ids) > 0:
            LockTable.objects.filter(id__in=self.lock_ids).update(locked=False)

    def __lock_names(self):
        can_lock = True
        names_in_db = set()
        # Get all created models in table with names in self.block
        for l in LockTable.objects.filter(name__in=self.names):
            names_in_db.add(l.name)
            self.lock_ids.add(l.id)
            if l.locked:
                can_lock = False

        # Are there models which aren't created yet?
        if len(names_in_db) < len(self.names):
            # Will be executed maximum 1 time per view function
            for l_name in set(self.names) - set(names_in_db):
                self.lock_ids.add(LockTable.objects.create(name=l_name).id)

        if not can_lock:
            while LockTable.objects.filter(id__in=self.lock_ids, locked=True).count() > 0:
                time.sleep(0.2)
                self.waiting_time[1] += 0.2
                if self.waiting_time[1] > MAX_WAITING:
                    if settings.UNLOCK_FAILED_REQUESTS:
                        break
                    raise RuntimeError('Not enough time to lock execution of view')
        # Lock
        LockTable.objects.filter(id__in=self.lock_ids).update(locked=True)

    def __get_affected_models(self, groups):
        block = set()
        for group in groups:
            if isinstance(group, ModelBase):
                block |= self.__affected_models(group)
            else:
                block.add(str(group))
        return block

    def __affected_models(self, model):
        curr_name = getattr(model, '_meta').object_name
        related_models = {curr_name}
        for rel in [f for f in getattr(model, '_meta').get_fields()
                    if (f.one_to_one or f.one_to_many) and f.auto_created and not f.concrete]:
            rel_model_name = getattr(rel.field.model, '_meta').object_name
            if rel_model_name not in related_models and rel_model_name != curr_name:
                related_models.add(rel_model_name)
                related_models |= self.__affected_models(rel.field.model)
        return related_models


def unparallel_group(groups):
    def __inner(f):

        def wait(*args, **kwargs):
            call_data = CallLogs(name=f.__name__, enter_time=time.time())
            locker = ExecLocker(groups)
            locker.lock()
            call_data.execution_time = time.time()
            try:
                res = f(*args, **kwargs)
            except Exception:
                call_data.execution_delta = time.time() - call_data.execution_time
                call_data.is_failed = True
                if settings.UNLOCK_FAILED_REQUESTS:
                    locker.unlock()
                raise
            else:
                call_data.execution_delta = time.time() - call_data.execution_time
                call_data.is_failed = False
                locker.unlock()
            finally:
                call_data.return_time = time.time()
                call_data.wait1 = locker.waiting_time[0]
                call_data.wait2 = locker.waiting_time[1]
                call_data.save()
            return res

        return wait

    return __inner


class LoggedCallMixin:
    unparallel = []

    def dispatch(self, request, *args, **kwargs):
        if not hasattr(super(), 'dispatch'):
            # This mixin should be used together with View based class
            raise BridgeException()

        call_data = CallLogs(name=type(self).__name__, enter_time=time.time())
        locker = ExecLocker(self.unparallel)
        locker.lock()
        call_data.execution_time = time.time()
        try:
            response = getattr(super(), 'dispatch')(request, *args, **kwargs)
        except Exception:
            call_data.execution_delta = time.time() - call_data.execution_time
            call_data.is_failed = True
            if settings.UNLOCK_FAILED_REQUESTS:
                locker.unlock()
            raise
        else:
            call_data.execution_delta = time.time() - call_data.execution_time
            call_data.is_failed = False
            locker.unlock()
        finally:
            call_data.return_time = time.time()
            call_data.wait1 = locker.waiting_time[0]
            call_data.wait2 = locker.waiting_time[1]
            call_data.save()
        return response

    def is_not_used(self, *args, **kwargs):
        pass


class ProfileData:
    def get_statistic_around(self, date, delta_seconds=300):
        date = self.__date_stamp(date)
        if date is None:
            raise ValueError('Wrong date format')
        return self.__collect_statistic(date - delta_seconds, date + delta_seconds, None)

    def get_statistic(self, date1=None, date2=None, func_name=None):
        date1 = self.__date_stamp(date1)
        date2 = self.__date_stamp(date2)
        return self.__collect_statistic(date1, date2, func_name)

    def get_log_around(self, date, delta_seconds=300):
        date = self.__date_stamp(date)
        if date is None:
            raise ValueError('Wrong date format')
        return self.get_log(date - delta_seconds, date + delta_seconds)

    def get_log(self, date1=None, date2=None, func_name=None):
        filters = {}
        date1 = self.__date_stamp(date1)
        if isinstance(date1, float):
            filters['enter_time__gt'] = date1
        date2 = self.__date_stamp(date2)
        if isinstance(date2, float):
            filters['enter_time__lt'] = date2
        if isinstance(func_name, str):
            filters['name'] = func_name
        logdata = []
        for call_data in CallLogs.objects.filter(**filters).order_by('id'):
            logdata.append({
                'name': call_data.name,
                'wait1': (call_data.wait1, call_data.wait1 > MAX_WAITING),
                'wait2': (call_data.wait2, call_data.wait2 > MAX_WAITING),
                'wait_total': call_data.wait1 + call_data.wait2,
                'enter': datetime.fromtimestamp(call_data.enter_time),
                'exec': datetime.fromtimestamp(call_data.execution_time),
                'return': datetime.fromtimestamp(call_data.return_time),
                'exec_time': '%0.3f' % call_data.execution_delta,
                'failed': call_data.is_failed
            })
        return logdata

    def __collect_statistic(self, date1, date2, func_name):
        self.__is_not_used()
        data = {}
        filters = {}
        if isinstance(date1, float):
            filters['enter_time__gt'] = date1
        if isinstance(date2, float):
            filters['enter_time__lt'] = date2
        if isinstance(func_name, str):
            filters['name'] = func_name

        for call_data in CallLogs.objects.filter(**filters).order_by('id'):
            if call_data.name not in data:
                data[call_data.name] = {
                    'name': call_data.name,
                    'total_exec': call_data.execution_delta,
                    'max_exec': call_data.execution_delta,
                    'waiting': call_data.wait1 + call_data.wait2,
                    'max_wait1': call_data.wait1,
                    'max_wait2': call_data.wait2,
                    'calls': 1,
                    'failed': 1 if call_data.is_failed else 0
                }
            else:
                data[call_data.name]['total_exec'] += call_data.execution_delta
                data[call_data.name]['waiting'] += call_data.wait1 + call_data.wait2
                data[call_data.name]['max_exec'] = max(data[call_data.name]['max_exec'], call_data.execution_delta)
                data[call_data.name]['max_wait1'] = max(data[call_data.name]['max_wait1'], call_data.wait1)
                data[call_data.name]['max_wait2'] = max(data[call_data.name]['max_wait2'], call_data.wait2)
                data[call_data.name]['calls'] += 1
                if call_data.is_failed:
                    data[call_data.name]['failed'] += 1
        for func in data:
            data[func]['average_exec'] = data[func]['total_exec'] / data[func]['calls']
        return list(data[fname] for fname in sorted(data))

    def __date_stamp(self, date):
        self.__is_not_used()
        if isinstance(date, datetime):
            date = date.timestamp()
        elif isinstance(date, time.struct_time):
            date = time.mktime(date)
        elif not isinstance(date, float):
            date = None
        return date

    def __is_not_used(self):
        pass


def clear_old_logs():
    # 30 days exactly
    border_time = time.time() - 2592000
    CallLogs.objects.filter(enter_time__lt=border_time).delete()
