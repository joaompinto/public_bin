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

import sys
import os
import paramiko
import select
import termios
import tty
import signal
import struct
import fcntl
import errno
import socket
import threading
import time
import os.path
from array import array
from os.path import expanduser, join, dirname, realpath 
from commands import getstatusoutput
from forward import FordwardTunnel
from random import randint

PKEEP_PATH = join(dirname(realpath(__file__)), 'pkeep.py')

def get_password(url):
	if not PKEEP_PATH:
		password = getpass("Password for %s: " % url)
		return password
	(rc, password) = getstatusoutput(PKEEP_PATH+' get %s' % url)
	if rc == 0 and len(password) < 8:
		print "Invalid stored password for", url,"!!!"
		sys.exit(5)
	if rc != 0:
		print "Password not found on pkeeper, prompt and save it."
		password = getpass("Password for %s: " % url)
		if not set_password(url, password):
			raise RuntimeError, 'Failed to store password'
	else:
		print "Using stored password"
	return password
      
def interactive_shell(chan):
    signal.signal(signal.SIGWINCH, sigwinch_passthrough)
    oldtty = termios.tcgetattr(sys.stdin)
    # Resize channel pty to match stdin size    
    #chan.resize_pty(w, h)    
    try:
        tty.setraw(sys.stdin.fileno())
        tty.setcbreak(sys.stdin.fileno())
        chan.settimeout(0.0)
        # set stdin to non blocking, read multiple chars (paste)
        fd = sys.stdin
        fl = fcntl.fcntl(fd, fcntl.F_GETFL)
        fcntl.fcntl(fd, fcntl.F_SETFL, fl | os.O_NONBLOCK)        
        while True:
            try:
                r, w, e = select.select([chan, sys.stdin], [], [])                
            except select.error, e: # don't raise on sigwinch                
                if e.args[0] != errno.EINTR: raise
            if chan in r:
                try:
                    x = chan.recv(1024)
                    if len(x) == 0:
                        print "*** Connection terminated\r"
                        break
                    sys.stdout.write(x)
                    sys.stdout.flush()
                except socket.timeout:
                    pass
            if sys.stdin in r:
                x = sys.stdin.read(4096)
                if len(x) == 0:
                    break
                result = chan.sendall(x)
                
    finally:
        termios.tcsetattr(sys.stdin, termios.TCSADRAIN, oldtty)

# SIGWINCH needs to be send to the child when the parent is resized
def sigwinch_passthrough (sig, data):
    global chan
    h , w = array('h', fcntl.ioctl(sys.stdin,termios.TIOCGWINSZ,'\0'*8))[:2]
    chan.resize_pty(w, h)
    return True
    
def wait_for_data(chan, options):
	data = ""
	while True:
		x = chan.recv(1024)
		if len(x) == 0:
			print "*** Connection terminated\r"
			sys.exit(3)	
		data += x
		sys.stdout.write(x)
		sys.stdout.flush()
		for i in range(len(options)):
			if options[i] in data:
				return i
	return -1

# Check command line
if len(sys.argv) < 2:
	print 'Usage: %s [[username]@]hostname' % sys.argv[0]
	sys.exit(2)

if sys.argv[1].find('@') == -1:	
	hostname = sys.argv[1]
	forced_p_user_id = None
	do_sudo = True
else:
	forced_p_user_id, hostname = sys.argv[1].split('@', 1)
	if forced_p_user_id:
		if forced_p_user_id == "root":
			forced_p_user_id = " "
		do_sudo = True
	else:
		do_sudo = False

if forced_p_user_id == '.':
	do_sudo = False

username = os.getenv('USER')

# Check IP and product_id from the hosts table
p_user_id = tunnel_proxy = connect_proxy = target_ip = None
hosts_fn = os.path.expanduser('~/etc/hosts')	
with open(hosts_fn, 'r') as hosts_file:
	hosts = hosts_file.read().splitlines()
for host in hosts:
	items = host.rsplit('#', 1)[0].split()
	if items[0] == hostname:
		target_ip = items[1]
		if len(items) > 2:
			p_user_id = items[2]
		if len(items) > 3:
			tunnel_proxy, connect_proxy = items[3].split(':')		
		break	

if not target_ip:
	print "Host",hostname,"not found on ~/etc/hosts"
	sys.exit(10)

p_user_id = forced_p_user_id or p_user_id
if not p_user_id:
	p_user_id = username

print "Connecting to %s [%s] %s" % \
  (hostname, target_ip, "using proxy "+tunnel_proxy if tunnel_proxy else "")
  
ssh = paramiko.SSHClient()
paramiko.util.log_to_file('/tmp/shell.log')
ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
target_hostname = connect_proxy or target_ip
target = "%s@%s" % (username, target_hostname)
(rc, password) = getstatusoutput(PKEEP_PATH+' get %s' % target)
connect_ip = tunnel_proxy or target_ip
ssh.connect(connect_ip, look_for_keys=False, 
	username=username, password=password)
h , w = array('h', fcntl.ioctl(sys.stdin,termios.TIOCGWINSZ,'\0'*8))[:2]
chan = ssh.invoke_shell(term=os.getenv('TERM') or 'vt100', width=w, height=h) 
tun = None
if tunnel_proxy:
	tunnel_port = randint(2000, 40000)
	tun = FordwardTunnel(tunnel_port, target_ip, 22, ssh.get_transport())
	tun.start()
	tunnel_port = None
	while tunnel_port is None:
		time.sleep(10/1000.0)
		tunnel_port = tun.local_port
	target = "%s@%s" % (username, hostname)
	(rc, password) = getstatusoutput(PKEEP_PATH+' get %s' % target)	
	ssh.connect('localhost', tunnel_port, look_for_keys=False,
		username=username, password=password)
	chan = ssh.invoke_shell(term=os.getenv('TERM') or 'vt100', width=w, height=h) 
#chan.sendall("Connected"+'\b'*len("Connected"))
#wait_for_data(chan, "Connected");
interactive_shell(chan)
if tun:
	tun.shutdown()
