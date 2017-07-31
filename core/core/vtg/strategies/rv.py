#!/usr/bin/python3

import glob
import shutil
import os
import re

from core.vtg.libraries.common import create_task, submit_task, wait_for_submitted_tasks, process_result
from core.vtg.strategies import Strategy

REGRESSION_VERIFICATION_TAG = "regression verification"
RV_MODE_TAG = "mode"
RV_INFO_FILE_TAG = "info file"
RV_POOL_TAG = "pool"
RV_PRIMARY_CONFIG_TAG = "primary config"
RV_SECONDARY_CONFIG_TAG = "secondary config"
RV_AUX_CONFIG_TAG = "aux config"
RV_MODE_SAVE = "save"
RV_MODE_LOAD = "load"
RV_MODE_UPDATE = "update"
RV_BASE_CONFIG = "<BASE>"
RV_GENERAL_SEPARATOR = ";"
RV_ASSERTION_SEPARATOR = ","


class RV(Strategy):
    long_name = "regression verification"
    name = "RV"

    def execute(self):
        launches = self.__get_rv_information()
        specified_assertions = set()
        submitted_tasks = []
        verification_task = None
        for launch in launches:
            verification_task, overall_assertions = create_task(self, predefined_config=launch.get("config"),
                                                                specified_assertions=specified_assertions or
                                                                                     launch.get("unks"))
            verification_task.assemble_task_files(verification_task.get_assertions())
            verification_task.execute_cil()
            submitted_tasks.append(submit_task(verification_task, self))
            if "unks" in launch:
                specified_assertions = set(overall_assertions) - launch.get("unks")
                if specified_assertions == set():
                    break
        verification_result = wait_for_submitted_tasks(submitted_tasks, self)
        process_result(verification_result, self, verification_task)

    def __get_rv_information(self):

        name = ""
        # TODO: should be more easier to obtain module name (same in create_task)
        for attr in self.conf['abstract task desc']['attrs']:
            attr_name = list(attr.keys())[0]
            attr_val = attr[attr_name]
            if attr_name == 'verification object':
                name = attr_val

        task_config = self.conf['VTG strategy']['verifier']
        if REGRESSION_VERIFICATION_TAG not in task_config:
            raise RuntimeError("Tag {0} must present for strategy {1}".format(REGRESSION_VERIFICATION_TAG, self.name))
        mode = task_config[REGRESSION_VERIFICATION_TAG][RV_MODE_TAG]
        info_file = task_config[REGRESSION_VERIFICATION_TAG][RV_INFO_FILE_TAG]
        pool = task_config[REGRESSION_VERIFICATION_TAG][RV_POOL_TAG]
        primary_config = task_config[REGRESSION_VERIFICATION_TAG][RV_PRIMARY_CONFIG_TAG]
        if mode == RV_MODE_SAVE:
            # aux_config = task_config[REGRESSION_VERIFICATION_TAG][RV_AUX_CONFIG_TAG]
            if not os.path.isfile(info_file):
                open(info_file, 'w').close()
            # TODO: implement it
            raise NotImplementedError("Not supported")
        elif mode == RV_MODE_LOAD:
            for file in glob.glob(os.path.join(pool, '{0}*'.format(re.sub(r'/', '-', name)))):
                shutil.copy(file, ".")
            secondary_config = task_config[REGRESSION_VERIFICATION_TAG][RV_SECONDARY_CONFIG_TAG]
            with open(info_file) as f_info:
                for line in f_info:
                    if name in line:
                        (name, config, unks) = line.rstrip().split(RV_GENERAL_SEPARATOR)
                        result = []
                        if config == RV_BASE_CONFIG:
                            if unks:
                                unknown_assertions = set(unks.split(RV_ASSERTION_SEPARATOR))
                                # TODO: get rid of it
                                if "linux:alloc:spin lock" in unknown_assertions and "linux:spinlock" \
                                        not in unknown_assertions:
                                    unknown_assertions.add("linux:spinlock")
                                if "linux:spinlock" in unknown_assertions and "linux:alloc:spin lock" \
                                        not in unknown_assertions:
                                    unknown_assertions.add("linux:alloc:spin lock")
                                result.append({"config": secondary_config, "unks": unknown_assertions})
                            result.append({"config": primary_config})
                        else:
                            result.append({"config": config})
                        return result
            # No information was found, use default config.
            return [{"config": secondary_config}]
        else:
            raise RuntimeError("Mode {0} is not supported in {1}".format(mode, self.long_name))
