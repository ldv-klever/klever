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

#include <linux/module.h>
#include <linux/net.h>
#include <ldv/linux/emg/test_model.h>
#include <ldv/verifier/nondet.h>

int ldv_create(struct net *net, struct socket *sock, int protocol, int kern)
{
	return 0;
}

int ldv_release(struct socket *sock)
{
    ldv_invoke_reached();
    return 0;
}

int ldv_bind(struct socket *sock, struct sockaddr *myaddr, int sockaddr_len)
{
    ldv_invoke_reached();
    return 0;
}

static struct net_proto_family ldv_driver = {
    .family = 5,
	.create = ldv_create
};

struct proto_ops ldv_proto_ops = {
    .bind = ldv_bind,
    .release = ldv_release
};

static int __init ldv_init(void)
{
	ldv_invoke_test();
	return sock_register(& ldv_driver);
}

static void __exit ldv_exit(void)
{
	sock_unregister(5);
}

module_init(ldv_init);
module_exit(ldv_exit)

MODULE_LICENSE("GPL");
