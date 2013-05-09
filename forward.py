#!/usr/bin/env python
# -*- coding: utf-8 -*- 
""" 
Copyright (c) 2013, João Pinto <lamego.pinto@gmail.com>
All rights reserved.

Redistribution and use in source and binary forms, with or without
modification, are permitted provided that the following conditions are met: 

1. Redistributions of source code must retain the above copyright notice, this
   list of conditions and the following disclaimer. 
2. Redistributions in binary form must reproduce the above copyright notice,
   this list of conditions and the following disclaimer in the documentation
   and/or other materials provided with the distribution. 

THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS" AND
ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE IMPLIED
WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT OWNER OR CONTRIBUTORS BE LIABLE FOR
ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL DAMAGES
(INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR SERVICES;
LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER CAUSED AND
ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY, OR TORT
(INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE OF THIS
SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.

The views and conclusions contained in the software and documentation are those
of the authors and should not be interpreted as representing official policies, 
either expressed or implied, of the FreeBSD Project.
"""

import getpass
import os
import socket
import select
import SocketServer
import sys
import threading
from optparse import OptionParser

import paramiko

g_verbose = False


class ForwardServer (SocketServer.ThreadingTCPServer):
    daemon_threads = True
    allow_reuse_address = True
    

class Handler (SocketServer.BaseRequestHandler):

    def handle(self):
        try:
            chan = self.ssh_transport.open_channel('direct-tcpip',
                                                   (self.chain_host, self.chain_port),
                                                   self.request.getpeername())
        except Exception, e:
            verbose('Incoming request to %s:%d failed: %s' % (self.chain_host,
                                                              self.chain_port,
                                                              repr(e)))
            return
        if chan is None:
            verbose('Incoming request to %s:%d was rejected by the SSH server.' %
                    (self.chain_host, self.chain_port))
            return

        verbose('Connected!  Tunnel open %r -> %r -> %r' % (self.request.getpeername(),
                                                            chan.getpeername(), (self.chain_host, self.chain_port)))
        while True:
            r, w, x = select.select([self.request, chan], [], [])
            if self.request in r:
                data = self.request.recv(1024)
                if len(data) == 0:
                    break
                chan.send(data)
            if chan in r:
                data = chan.recv(1024)
                if len(data) == 0:
                    break
                self.request.send(data)
        chan.close()
        self.request.close()
        verbose('Tunnel closed from %r' % (self.request.getpeername(),))


class FordwardTunnel (threading.Thread):
	
	def __init__(self, local_port, remote_host, remote_port, transport):
		self.assigned_port = None
		self.local_port = local_port
		self.remote_host = remote_host
		self.remote_port = remote_port
		self.transport = transport
		threading.Thread.__init__(self)
		
	def run(self):
		# this is a little convoluted, but lets me configure things for the Handler
		# object.  (SocketServer doesn't give Handlers any way to access the outer
		# server normally.)
		class SubHander (Handler):
			chain_host = self.remote_host
			chain_port = self.remote_port
			ssh_transport = self.transport
		retry_count = 3
		while retry_count > 0:
			try:
				self.server = ForwardServer(('', self.local_port), SubHander)
			except socket.error as err:
				if err.errno == 98:
					print "Trying next port"
					pass
				else:
					raise
			else:
					break
			retry_count -= 1
			self.local_port += 1
		if retry_count == 0:
			self.assigned_port = 0
		else:
			self.assigned_port = self.local_port
			self.server.serve_forever()
		
	def shutdown(self):
		self.server.shutdown()


def verbose(s):
    if g_verbose:
        print s
