#
# Copyright (c) 2022 ISP RAS (http://www.ispras.ru)
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

CC = gcc
# Without main() it is necessary to provide following compiler options: -nostartfiles -Wl,--entry=start
CFLAGS = -Iinclude -Wall -Werror
DEPS = kernel.h modules.h
OBJS = kernel/start.o kernel/resource.o \
       modules/simple/simple.o \
       modules/simple-double-allocation/simple-double-allocation.o \
       modules/simple-no-check/simple-no-check.o \
       modules/simple-no-release/simple-no-release.o \
       modules/complex/main.o modules/complex/allocate.o modules/complex/release.o

.PHONY: all clean

all: simple-os

simple-os: $(OBJS)
	$(CC) $(CFLAGS) $^ -o $@

%.o: %.c $(DEPS)
	$(CC) $(CFLAGS) -c $< -o $@

clean:
	rm -f simple-os $(OBJS)
