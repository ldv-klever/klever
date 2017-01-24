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
import csv
import glob
import time
from datetime import datetime
from django.db.models.base import ModelBase
from tools.models import LockTable

# Waiting while other function try to lock with DB table + try to lock with DB table
# So maximum waiting time is (MAX_WAITING * 2) in seconds.
MAX_WAITING = 30


class ExecLocker:
    lockfile = os.path.join('media', '.lock')

    def __init__(self, groups):
        self.names = self.__get_affected_models(groups)
        self.lock_ids = set()
        # wait1 and wait2
        self.waiting_time = [0.0, 0.0]

    def lock(self):
        # Lock with file while we locking with DB table
        while os.path.exists(self.lockfile):
            time.sleep(0.1)
            self.waiting_time[0] += 0.1
            if self.waiting_time[0] > MAX_WAITING:
                self.__waiting_time_passed()
                break
        with open(self.lockfile, mode='x'):
            pass

        try:
            self.__lock_names()
        finally:
            os.remove(self.lockfile)

    def unlock(self):
        LockTable.objects.filter(id__in=self.lock_ids).update(locked=False)

    def __waiting_time_passed(self):
        pass

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
                    self.__waiting_time_passed()
                    break
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


def profiling(row):
    csv_file = os.path.join('media', 'CSV', time.strftime('%Y-%m-%d.csv'))
    os.makedirs(os.path.dirname(csv_file), exist_ok=True)
    with open(csv_file, mode='a', newline='') as csvfile:
        # func_name - The name of view function
        # enter - time when response processing started
        # exec - time when view function was called
        # exec_time - view function execution time
        # return - time when response processing ended by Django
        # wait1 - waiting time while other function tries to lock with DB table
        # wait2 - waiting time while trying to lock with DB table
        fieldnames = ['func_name', 'enter', 'exec', 'is_failed', 'exec_time', 'return', 'wait1', 'wait2']
        writer = csv.writer(csvfile, delimiter=',')
        if csvfile.tell() == 0:
            writer.writerow(fieldnames)
        writer.writerow(row)


def unparallel_group(groups):
    def __inner(f):

        def wait(*args, **kwargs):
            profiling_row = [f.__name__, time.time()]
            locker = ExecLocker(groups)
            locker.lock()
            profiling_row.append(time.time())
            t1 = time.time()
            try:
                res = f(*args, **kwargs)
            except Exception:
                profiling_row.append(1)
                raise
            finally:
                profiling_row.append(0)
                profiling_row.append(time.time() - t1)
                locker.unlock()
                profiling_row.append(time.time())
                profiling_row.extend(locker.waiting_time)
                profiling(profiling_row)
            return res

        return wait

    return __inner


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

    def get_log(self, date1=None, date2=None):
        logdata = []
        date1 = self.__date_stamp(date1)
        date2 = self.__date_stamp(date2)
        first_file = self.__get_file(date1)
        last_file = self.__get_file(date2)
        for fname in self.__get_files(date1, date2):
            bname = os.path.basename(fname)
            with open(fname, mode='r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    row = self.__get_data(row)
                    if bname == first_file and row['enter'] < date1:
                        continue
                    if bname == last_file and row['return'] > date2:
                        continue
                    logdata.append({
                        'name': row['func_name'],
                        'wait1': (row['wait1'], row['wait1'] > MAX_WAITING),
                        'wait2': (row['wait2'], row['wait2'] > MAX_WAITING),
                        'wait_total': row['wait1'] + row['wait2'],
                        'enter': (str(row['enter']), datetime.fromtimestamp(row['enter'])),
                        'exec': (str(row['exec']), datetime.fromtimestamp(row['exec'])),
                        'return': (str(row['return']), datetime.fromtimestamp(row['return'])),
                        'exec_time': '%0.3f' % row['exec_time'],
                        'failed': bool(int(row['is_failed']))
                    })
        return logdata

    def __collect_statistic(self, date1, date2, func_name):
        data = {}
        first_file = self.__get_file(date1)
        last_file = self.__get_file(date2)
        for fname in self.__get_files(date1, date2):
            bname = os.path.basename(fname)
            with open(fname, mode='r') as csvfile:
                reader = csv.DictReader(csvfile)
                for row in reader:
                    row = self.__get_data(row)
                    if bname == first_file and row['enter'] < date1:
                        continue
                    if bname == last_file and row['return'] > date2:
                        continue
                    if func_name is not None and row['func_name'] != func_name:
                        continue
                    func = row['func_name']
                    if func not in data:
                        data[func] = {
                            'name': func,
                            'exec': row['exec_time'],
                            'waiting': row['wait1'] + row['wait2'],
                            'calls': 1,
                            'failed': 1 if row['is_failed'] else 0
                        }
                    else:
                        data[func]['exec'] = (data[func]['exec'] * data[func]['calls'] + row['exec_time']) / \
                                             (data[func]['calls'] + 1)
                        data[func]['waiting'] += row['wait1'] + row['wait2']
                        data[func]['calls'] += 1
                        if row['is_failed']:
                            data[func]['failed'] += 1
        return list(data[fname] for fname in sorted(data))

    def __get_files(self, date1, date2):
        files = set()
        first_file = self.__get_file(date1)
        for fname in glob.glob(os.path.join('media', 'CSV', '*.csv')):
            bname = os.path.basename(fname)
            file_time = time.mktime(time.strptime(bname, '%Y-%m-%d.csv'))
            if date1 is not None and date1 > file_time and bname != first_file:
                continue
            if date2 is not None and date2 < file_time:
                continue
            files.add(fname)
        return sorted(files)

    def __date_stamp(self, date):
        self.__is_not_used()
        if isinstance(date, datetime):
            date = date.timestamp()
        elif isinstance(date, time.struct_time):
            date = time.mktime(date)
        elif not isinstance(date, float):
            date = None
        return date

    def __get_file(self, date):
        self.__is_not_used()
        fname = None
        if isinstance(date, float):
            fname = time.strftime('%Y-%m-%d.csv', time.localtime(date))
        return fname

    def __get_data(self, row):
        self.__is_not_used()
        row['enter'] = float(row['enter'])
        row['exec'] = float(row['exec'])
        row['exec_time'] = float(row['exec_time'])
        row['is_failed'] = bool(int(row['is_failed']))
        row['return'] = float(row['return'])
        row['wait1'] = float(row['wait1'])
        row['wait2'] = float(row['wait2'])
        return row

    def __is_not_used(self):
        pass
