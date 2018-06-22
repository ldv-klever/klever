/*
 * Copyright (c) 2018 ISP RAS (http://www.ispras.ru)
 * Ivannikov Institute for System Programming of the Russian Academy of Sciences
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *   http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * ee the License for the specific language governing permissions and
 * limitations under the License.
 */

union ldv_union1 {
	int field1;
	int field2;
	int field3;
};

union ldv_union2 {
	union ldv_union1 field;
};

union ldv_union3 {
	union ldv_union2 field;
};

union ldv_union4 {
	union ldv_union3 field;
};

union ldv_union5 {
	union ldv_union4 field;
};

union ldv_union6 {
	union ldv_union5 field;
};

union ldv_union7 {
	union ldv_union6 field;
};

union ldv_union8 {
	union ldv_union7 field;
};

union ldv_union9 {
	union ldv_union8 field;
};

union ldv_union10 {
	union ldv_union9 field;
};
