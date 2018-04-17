#!/usr/bin/python

import os
import re
import argparse
import json
import json.load as load
import json.dump as dump
# def dump(obj, fh):
#	  fh.write(dumps(obj))
# s - object | _ - file
from subprocess import run, Popen, PIPE

def _init(file=None, configuration=None):
	"""
	:param file: File with the configuration. Do not set the option alongside with the configuration one.
	:param configuration: The configuration dictionary. Do not set the option alongside with the file one.
	:return: #hamster CHECK: 
	"""

	# check configuration being
	if configuration and file:
		raise ValueError('Provide either file or configuration string')
	elif file:
		with open(file, encoding="utf8") as fh:
			conf = json.loads(fh.read())
	elif configuration:
		conf = configuration
	else:
		raise ValueError('Provide any file or configuration string')

	# check image config
	if not "Image Config" in conf:
		raise KeyError("Provide configuration property 'Image Config' as an JSON-object")

	# check image base - image_base
	if not "image base" in conf["Image Config"]:
		raise KeyError("Provide configuration property 'image base' as an JSON-object")
	# check empty value
	elif conf["Image Config"]["image base"]:
		image_base = conf["Image Config"]["image base"]
	else:
		image_base = "debian:latest"

	# check path
	# check path type - path_type
	if not "path type" in conf["Image Config"]:
		raise KeyError("Provide configuration property 'path type' as an JSON-object")
	# check build path - build_path
	elif not "build path" in conf["Image Config"]:
		raise KeyError("Provide configuration property 'build path' as an JSON-object")
	else:
		path_type = conf["Image Config"]["path type"]
		# if not ( (path_type == "absolute") or (path_type == "relative") ):
		if path_type not in ('absolute', 'relative'):
			raise ValueError("Provide right path type")
		else:
			#		path_type_val = True if path relative
			# and	path_type_val = False if absolute
			path_type_val = path_type == "relative"
		build_path = conf["Image Config"]["build path"]
		if (not path_type_val and not build_path[0] == '/') or (path_type_val and build_path[0] == '/'):
			raise ValueError("Check build_path: if it absolute then start with '/' else if it relative then start without '/'")

	# check port - port
	if not "port" in conf["Image Config"]:
		raise KeyError("Provide configuration property 'port' as an JSON-object")
	# check empty value
	elif conf["Image Config"]["port"]:
		port = conf["Image Config"]["port"]
	else:
		raise ValueError("Provide existing port in configuration")

	# check Klever Core information
	if not "Klever Core" in conf["Image Config"]:
		raise KeyError("Provide configuration property 'Klever Core' as an JSON-object")
	# check do we need Klever Core in image
	elif not "using" in conf["Image Config"]["Klever Core"]:
		raise KeyError("Provide configuration property 'Klever Core':'using' as an JSON-object")
	elif conf["Image Config"]["Klever Core"]["using"]:
		klever_using = True
		# check Klever Core version
		if not "version" in conf["Image Config"]["Klever Core"]:
			raise KeyError("Provide configuration property 'Klever Core':'version' as an JSON-object")
		elif not "path" in conf["Image Config"]["Klever Core"]:
			raise KeyError("Provide configuration property 'Klever Core':'path' as an JSON-object")
		elif not "executable path" in conf["Image Config"]["Klever Core"]:
			raise KeyError("Provide configuration property 'Klever Core':'executable path' as an JSON-object")
		else:
			klever_version = conf["Image Config"]["Klever Core"]["version"]
			klever_path = conf["Image Config"]["Klever Core"]["path"]
			klever_exec_path = conf["Image Config"]["Klever Core"]["executable path"]
	else klever_using = False

	# check CPAchecker information
	if not "CPAchecker" in conf["Image Config"]:
		raise KeyError("Provide configuration property 'CPAchecker' as an JSON-object")
	# check do we need CPAchecker in image
	elif not "using" in conf["Image Config"]["CPAchecker"]:
		raise KeyError("Provide configuration property 'CPAchecker':'using' as an JSON-object")
	elif conf["Image Config"]["CPAchecker"]["using"]:
		cpachecker_using = True
		# check name of archive with CPAchecker binaries
		if not "tar name" in conf["Image Config"]["CPAchecker"]:
			raise KeyError("Provide configuration property 'CPAchecker':'tar name' as an JSON-object")
		# check CPAchecker version: branch and revision
		elif not "version" in conf["Image Config"]["CPAchecker"]:
			raise KeyError("Provide configuration property 'CPAchecker':'version' as an JSON-object") #hamster CHECK: проверить что писать в кейэрор, весь путь до версии или только само слово версия
		# check CPAchecker path
		elif not "path" in conf["Image Config"]["CPAchecker"]:
			raise KeyError("Provide configuration property 'CPAchecker':'path' as an JSON-object")
		# check CPAchecker executable path
		elif not "executable path" in conf["Image Config"]["CPAchecker"]:
			raise KeyError("Provide configuration property 'CPAchecker':'executable path' as an JSON-object")
		else:
			tar_name = conf["Image Config"]["CPAchecker"]["tar name"]
			cpachecker_version = conf["Image Config"]["CPAchecker"]["version"]
			if ":" in cpachecker_version:
				branch_name, branch_revision = cpachecker_version.split(':')
				# if branch name not trunk, then add "branches/" in the begining to switch on this branch right
				if not branch_name == "trunk":
					branch_name = "branches/" + branch_name
			# if not branch name, then use trunk
			else:
				branch_name = "trunk"
				branch_revision = cpachecker_version
			# check that revision is number
			if not branch_revision.isdigit():
				raise ValueError("Integer branch revision is expected")
			cpachecker_path = conf["Image Config"]["CPAchecker"]["path"]
			cpa_exec_path = conf["Image Config"]["CPAchecker"]["executable path"]
	else cpachecker_using = False

	# check BenchExec information
	if not "BenchExec" in conf["Image Config"]:
		raise KeyError("Provide configuration property 'BenchExec' as an JSON-object")
	# check do we need BenchExec in image
	elif not "using" in conf["Image Config"]["BenchExec"]:
		raise KeyError("Provide configuration property 'BenchExec':'using' as an JSON-object")
	elif conf["Image Config"]["BenchExec"]["using"]:
		benchexec_using = True
		# check BenchExec version
		if not "version" in conf["Image Config"]["BenchExec"]:
			raise KeyError("Provide configuration property 'BenchExec':'version' as an JSON-object")
		elif not "path" in conf["Image Config"]["BenchExec"]:
			raise KeyError("Provide configuration property 'BenchExec':'path' as an JSON-object")
		elif not "executable path" in conf["Image Config"]["BenchExec"]:
			raise KeyError("Provide configuration property 'BenchExec':'executable path' as an JSON-object")
		else:
			benchexec_version = conf["Image Config"]["BenchExec"]["version"]
			benchexec_path = conf["Image Config"]["BenchExec"]["path"]
			benchexec_exec_path = conf["Image Config"]["BenchExec"]["executable path"]
	else benchexec_using = False


	# configure enviroment

	# check current directory
	current_path = os.path.curdir
	# remember initial directory
	init_path = current_path

	# pass to working path - build_path
	if path_type_val: # if path relative
		current_path = os.path.join(current_path, build_path)
	else:
		current_path = build_path
	# save current build path
	current_build_path = current_path
	os.chdir(current_path)


	# configure enviroment Klever Core
	if klever_using:
		# pass to CPAchecker path
		current_path = os.path.join(current_build_path, klever_path)
		os.chdir(current_path)

		# save git branch
		process = Popen("git status", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
		vivod_stdout, error_stderr = process.communicate()
		if error_stderr:
			raise RuntimeError("Error then execute shell command 'git status': {}".format(error_stderr))
		# search name of current branch
		temp_git_branch_klever = re.search(r"On branch .*", vivod_stdout)
		if temp_git_branch_klever:
			saved_git_branch_klever = temp_git_branch_klever.group(0).split()[2]
		else:
			raise RuntimeError("Can't find branch name in the output of 'git status' shell command:\n{}".format(vivod_stdout)) 

		# switch on right git branch
		cmd = "git checkout" + klever_version
		run(cmd, shell=True) #hamster CHECK: проверить на ошибку, тобишь если такой ветки нет


	# configure enviroment CPAchecker
	if cpachecker_using:
		# pass to CPAchecker path
		current_path = os.path.join(current_build_path, cpachecker_path)
		os.chdir(current_path)

		# save current svn branch
		process = Popen("svn info", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
		vivod_stdout, error_stderr = process.communicate()
		if error_stderr:
			raise RuntimeError("Error then execute shell command 'svn info': {}".format(error_stderr))
		# seach current branch name
		temp_seach_br_name = re.search(r"Relative URL: \^/.*", vivod_stdout)
		if temp_seach_br_name:
			saved_branch_name = temp_seach_br_name.group(0).split()[2]
		else:
			raise RuntimeError("Can't find 'relative URL' in the output of 'svn info' shell command:\n{}".format(vivod_stdout))
		# seach current branch revision
		temp_seach_rev = re.search(r"Revision: [0-9]+", vivod_stdout)
		if temp_seach_rev:
			saved_revison = temp_seach_rev.group(0).split()[1]
		else:
			raise RuntimeError("Can't find 'revision' in the output of 'svn info' shell command:\n{}".format(vivod_stdout)) 

		# switch on right svn branch and revision
		cmd = "svn switch ^/" + branch_name
		run(cmd, shell=True)
		cmd = "svn up -r " + branch_revision
		run(cmd, shell=True)

		# make cpachecker .tar.bz2 archive
		cmd = "ant tar"
		run(cmd, shell=True)

		# check archive name
		process = Popen("ls", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
		vivod_stdout, error_stderr = process.communicate()
		if error_stderr:
			raise RuntimeError("Error then execute shell command 'ls': {}".format(error_stderr))
		# seach full archive name
		temp_seach_tar_name = re.search(r"CPAchecker.*tar\.bz2", vivod_stdout)
		if temp_seach_tar_name:
			find_tar_name = temp_seach_tar_name.group(0)
			if not find_tar_name == tar_name:
				raise ValueError("Wrong CPAchecker tar name in config, right name:{}".format(find_tar_name))
		else:
			raise RuntimeError("Can't find CPAchecker tar archive name in the output of 'ls' shell command:\n{}".format(vivod_stdout))

	# configure enviroment BenchExec
	if benchexec_using:
		# pass to CPAchecker path
		current_path = os.path.join(current_build_path, benchexec_path)
		os.chdir(current_path)

		# save git branch
		process = Popen("git status", stdout=PIPE, stderr=PIPE, universal_newlines=True, shell=True)
		vivod_stdout, error_stderr = process.communicate()
		if error_stderr:
			raise RuntimeError("Error then execute shell command 'git status': {}".format(error_stderr))
		# search name of current branch
		temp_git_branch_benchexec = re.search(r"On branch .*", vivod_stdout)
		if temp_git_branch_benchexec:
			saved_git_branch_name = temp_git_branch_benchexec.group(0).split()[2]
		else:
			raise RuntimeError("Can't find branch name in the output of 'git status' shell command:\n{}".format(vivod_stdout)) 

		# switch on right git branch
		cmd = "git checkout" + benchexec_version
		run(cmd, shell=True) #hamster CHECK: проверить на ошибку, тобишь если такой ветки нет


	# generation dockerfile
	current_path = current_build_path
	os.chdir(current_path)
	# make dockerfile and write into it
	with open("dockercpa_dockerfile", "w", encoding="utf8") as dockerfile:
		line = "#Installing parts: "
		if klever_using:
			line = line + "Klever Core | "
		if cpachecker_using:
			line = line + "CPAchecker | "
		if benchexec_using:
			line = line + "BenchExec | "
		line = line + "\n"
		dockerfile.write(line)
		# core system
		line = "FROM " + image_base + "\n"
		dockerfile.write(line)
		# enviroment
		line = '\nENV DEBIAN_FRONTEND = "noninteractive"\n'
		dockerfile.write(line)

		line = "\n# Upgrade installed packages\n"
		dockerfile.write(line)
		line = "RUN apt-get update && apt-get upgrade -y\n"
		dockerfile.write(line)
		if klever_using:
			line = "# For Python packages\n"
			dockerfile.write(line)
			line = "	libpq-dev python3-dev python3-pip /\n"
			dockerfile.write(line)
			line = "# For Klever Core\n"
			dockerfile.write(line)
			line = "	bc git graphviz /\n"
			dockerfile.write(line)
		if cpachecker_using:
			line = "# For CPAchecker 1.6+\n"
			dockerfile.write(line)
			line = "	openjdk-8-jre-headless /\n"
			dockerfile.write(line)
		line = "# For building the Linux kernel\n"
		dockerfile.write(line)
		line = "	make libc6-dev-i386 /\n"
		dockerfile.write(line)
		line = "# For building new versions of the Linux kernel\n"
		dockerfile.write(line)
		line = "	libssl-dev libelf-dev\n"
		dockerfile.write(line)

		if klever_using:
			line = "\n# Install Python packages\n"
			dockerfile.write(line)
			line = "RUN pip3 install -U /\n"
			dockerfile.write(line)
			line = "# For Klever Core\n"
			dockerfile.write(line)
			line = "	jinja2 grraphviz ply requests setuptools_scm /\n"
			dockerfile.write(line)
			line = "# For Klever Scheduler\n"
			dockerfile.write(line)
			line = "	consulate\n"
			dockerfile.write(line)
			line = "\n# Copy Klever Core binaries\n"
			dockerfile.write(line)
			line = "COPY " + klever_path + " klever/core\n"
			dockerfile.write(line)
			line = "\nENV PATH klever/core/" + klever_exec_path + ":$PATH\n"
			dockerfile.write(line)

		if cpachecker_using:
			line = "\n# Copy CPAchecker binaries\n"
			dockerfile.write(line)
			line = "# ADD will auto extract archive\n"
			dockerfile.write(line)
			line = 'ADD ["' + find_tar_name + '", "/"]\n'
			dockerfile.write(line)
			line = '\nENV PATH="' + find_tar_name.split(".tar.")[0] + '/' + cpa_exec_path + ':{$PATH}"\n'
			dockerfile.write(line)

		if benchexec_using:
			line = "\n# Copy BenchExec source code\n"
			dockerfile.write(line)
			line = "COPY " + benchexec_path + "/bin benchexec/bin\n"
			dockerfile.write(line)
			line = "COPY " + benchexec_path + "/benchexec benchexec/benchexec\n"
			dockerfile.write(line)
			line = "ENV PATH benchexec/" + benchexec_exec_path + ":$PATH\n"
			dockerfile.write(line)

		line = "\n# Expose port\n"
		dockerfile.write(line)
		line = "EXPOSE " + str(port) + "\n"
		dockerfile.write(line)

		line = "\n# Copy Klever scheduler to run client scr\n"
		dockerfile.write(line)
		line = "COPY klever/scheduler klever/scheduler\n"
		dockerfile.write(line)
		line = "WORKDIR /root/klever/scheduler/client\n"
		dockerfile.write(line)
		line = 'ENTRYPOINT ["python", "node_client.py"]\n'
		dockerfile.write(line)

	# not the end
