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

import os
import sys
import subprocess
import gpgme
from StringIO import StringIO
from commands import getstatusoutput
from getpass import getpass
from os.path import exists


# GPG public key used for the encryption, as displayed from 
# gpg --list-keys, e.g: pub   4096R/2733AB07
GPG_PUB_KEY = os.getenv('GPG_PUB_KEY')
if not GPG_PUB_KEY:
	print "You must set the environement variable GPG_PUB_KEY!"
	sys.exit(1)

# encrypted file location
STORE_FILE = os.path.expanduser('~/.pkeep.data')


available_commands = ['add','del','list','get', 'clipget', 'change', 'set', 'pset']
param_commands = ['change', 'get', 'clipget', 'del', 'change']

# We need GTK for the clipboard replacement
try:
	import gtk
except ImportError:
	del available_commands['clipget']

class PassStore():
	""" """
	def __init__(self, store_filename, keyid):
		self.items = {}
		self.store_filename = store_filename
		self.keyid = keyid
		self.ctx = ctx = gpgme.Context()
		ctx.armor = True
		self.key = key = ctx.get_key(keyid)
		if not exists(store_filename):
			print "Store file was not found."
			return
		with open(store_filename, 'r') as f:
			encrypted = StringIO(f.read())
		plain = StringIO()
		ctx.decrypt(encrypted, plain)
		data = plain.getvalue().splitlines()
		for line in data:
			(url, password) = line.split(' ',2)
			self.items[url] = password
						
	def add(self, url, password):
		self.items[url] = password
		
	def save(self):		
		store_filename = self.store_filename
		new_filename = store_filename + '.new'
		data = ''
		for url in self.items.keys():
			line = url+" "+self.items[url]+"\n"
			data += line
		cipher = StringIO()
		key = self.ctx.get_key(self.keyid)
		self.ctx.encrypt([key], 0, StringIO(data), cipher)
		with open(new_filename, 'w', 0600) as f:
			f.write(cipher.getvalue())
		os.rename(new_filename, store_filename)
			
pstore = PassStore(STORE_FILE, GPG_PUB_KEY)

if len(sys.argv) < 2:
	cmd = None
else:
	cmd = sys.argv[1]

	
if cmd not in available_commands or (cmd <> 'list' and len(sys.argv) < 3):
	if cmd not in available_commands:
		print "Uknown command", cmd
	else:
		print "Missing parameter for command ", cmd
	print "\nUsage: %s command url [parameters]" % sys.argv[0]
	print "Available commands: ", ','.join(available_commands)
	print """\nExamples: 
  pkeep.py add myuser@myserver.com
  pkeep.py get myuser@myserver.com get # Password printed to stdout
  pkeep.py clipget myuser@myserver.com clipget # Password available from the clipboard
  pkeep.py list myserver.com # 
	"""
	sys.exit(2)

if len(sys.argv) > 2:
	url = sys.argv[2]
else:
	url = None

if cmd in param_commands:
	if url not in pstore.items.keys():
		print url,"not stored!"
		sys.exit(4)

if cmd in [ 'add', 'change', 'set', 'pset']:
	if cmd == 'add' and url in pstore.items.keys():
		print url, "already stored!"
		sys.exit(3)
		
	if cmd == 'change':
		del pstore.items[url]
	if cmd in ['set', 'pset']:
		try:
			del pstore.items[url]
		except KeyError:
			pass
	if cmd == 'pset':
		password = sys.argv[3]
	else:
		password = getpass('Password for '+url+': ')
		if len(password) < 2:
			print "Password prompt aborted."
			sys.exit(10)
	pstore.add(url, password)
	pstore.save()
	print url, "added."
elif cmd == 'del':
	del pstore.items[url]
	pstore.save()
	print url,"deleted."
elif cmd in [ 'get', 'clipget']:
	password = pstore.items.get(url, None)	
	if cmd == 'get':
		print password
	else:
		clipboard = gtk.clipboard_get()	
		clipboard.set_text(password)
		clipboard.store()
elif cmd == 'list':
	found = 0
	for item in pstore.items:
		if url and item.find(url) == -1:
			continue
		found += 1
		print item
	sys.exit(found)
