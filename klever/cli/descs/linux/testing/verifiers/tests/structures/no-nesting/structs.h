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
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

struct ldv_struct1 {
	int field1;
	int field2;
	int field3;
};

struct ldv_struct2 {
	struct ldv_struct1 field;
};

struct ldv_struct3 {
	struct ldv_struct2 field;
};

struct ldv_struct4 {
	struct ldv_struct3 field;
};

struct ldv_struct5 {
	struct ldv_struct4 field;
};

struct ldv_struct6 {
	struct ldv_struct5 field;
};

struct ldv_struct7 {
	struct ldv_struct6 field;
};

struct ldv_struct8 {
	struct ldv_struct7 field;
};

struct ldv_struct9 {
	struct ldv_struct8 field;
};

struct ldv_struct10 {
	struct ldv_struct9 field;
};
