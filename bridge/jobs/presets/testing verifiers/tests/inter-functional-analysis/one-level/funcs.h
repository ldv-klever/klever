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

static inline int ldv_func1(int arg)
{
	return arg;
}

static inline int ldv_func2(int arg)
{
	return -ldv_func1(arg);
}

static inline int ldv_func3(int arg)
{
	return -ldv_func2(arg);
}

static inline int ldv_func4(int arg)
{
	return -ldv_func3(arg);
}

static inline int ldv_func5(int arg)
{
	return -ldv_func4(arg);
}

static inline int ldv_func6(int arg)
{
	return -ldv_func5(arg);
}

static inline int ldv_func7(int arg)
{
	return -ldv_func6(arg);
}

static inline int ldv_func8(int arg)
{
	return -ldv_func7(arg);
}

static inline int ldv_func9(int arg)
{
	return -ldv_func8(arg);
}

static inline int ldv_func10(int arg)
{
	return -ldv_func9(arg);
}
