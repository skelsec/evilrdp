import io
import enum
import os
import asyncio
from typing import Dict
from aardwolf.extensions.RDPEDYC.vchannels import VirtualChannelBase
from asysocks.protocol.socks5 import SOCKS5Method, SOCKS5NegoReply, \
	SOCKS5Request, SOCKS5Command, SOCKS5ReplyType, SOCKS5Reply

class PSCMD(enum.Enum):
	OK = 0
	ERR = 1
	CONTINUE = 2
	PS = 20
	GETFILE = 21
	PUTFILE = 22
	FILEDATA = 23
	SHELL = 24
	SHELLDATA = 25
	SOCKETOPEN = 26
	SOCKETDATA = 27

class PSCMDMessage:
	def __init__(self, command: PSCMD ,data:bytes, token:bytes = None, length:int = None):
		self.length = length
		self.token = token
		self.command = command
		self.data = data

	def to_bytes(self):
		if self.token is None:
			self.token = os.urandom(16)
		if self.length is None:
			self.length = len(self.data) + 24
		t = self.length.to_bytes(4, byteorder='little', signed=False)
		t += self.token
		t += self.command.value.to_bytes(4, byteorder='little', signed=False)
		t += self.data
		return t

	@staticmethod
	def from_bytes(data:bytes):
		return PSCMDMessage.from_buffer(io.BytesIO(data))
	
	@staticmethod
	def from_buffer(buff:io.BytesIO):
		length = int.from_bytes(buff.read(4), byteorder='little', signed=False)
		token = buff.read(16)
		command = PSCMD(int.from_bytes(buff.read(4), byteorder='little', signed=False))
		data = buff.read(length-24)
		return PSCMDMessage(command, data, token, length)
	
	def __str__(self):
		t = ''
		for k in self.__dict__:
			t += '%s: %s\r\n' % (k, self.__dict__[k])
		return t

class PSCMDChannel(VirtualChannelBase):
	def __init__(self, channelname):
		VirtualChannelBase.__init__(self, channelname)
		self.channel_active_evt = asyncio.Event()
		self.__socksserver = None
		self.__channels:Dict[bytes, asyncio.Queue[PSCMDMessage]] = {} # token -> Qeue
		self.__proxytasks = []

	async def channel_init(self):
		print('Channel init called!')
		self.channel_active_evt.set()
		for token in self.__channels:
			await self.__channels[token].put(PSCMDMessage(PSCMD.ERR, b'', token))
		return True, None

	async def channel_data_in(self, data:bytes):
		try:
			#print('DATA IN: %s' % data)
			msg = PSCMDMessage.from_bytes(data)
			if msg.token not in self.__channels:
				print('Message arrived from server with unknown token!')
				return
			await self.__channels[msg.token].put(msg)
		except Exception as e:
			print('Error! %s' % e)
			return

	async def channel_closed(self):
		print('Channel closed!')
		self.channel_active_evt = asyncio.Event()
		if self.__socksserver is not None:
			self.__socksserver.close()
			self.__socksserver = None
		

	async def sendcmd(self, cmd:PSCMDMessage):
		if cmd.token is None:
			cmd.token = os.urandom(16)
		self.__channels[cmd.token] = asyncio.Queue()
		await self.channel_data_out(cmd.to_bytes())
		return cmd.token

	async def sendrcv_pscmd(self, ps):
		cmd = PSCMDMessage(PSCMD.PS, ps.encode())
		token = await self.sendcmd(cmd)
		for _ in range(1):
			msg = await self.__channels[token].get()
			return msg.data.decode()

	async def sendrcv_getfile(self, filepath):
		cmd = PSCMDMessage(PSCMD.GETFILE, filepath.encode())
		token = await self.sendcmd(cmd)
		while True:
			msg = await self.__channels[token].get()
			if msg.command == PSCMD.OK:
				break
			elif msg.command == PSCMD.ERR:
				raise Exception('File read error!')
			elif msg.command == PSCMD.FILEDATA:
				yield msg.data.decode()
			else:
				raise Exception('Unexpected reply type %s' % msg.command)
	
	async def sendrcv_shellexec(self, command):
		cmd = PSCMDMessage(PSCMD.SHELL, command.encode())
		token = await self.sendcmd(cmd)
		while True:
			msg = await self.__channels[token].get()
			if msg.command == PSCMD.OK:
				break
			elif msg.command == PSCMD.ERR:
				raise Exception('Shell exec error!')
			elif msg.command == PSCMD.SHELLDATA:
				stderr_or_stout = int.from_bytes(msg.data[:4], byteorder='little', signed=False)
				line = ''
				if len(msg.data) > 4:
					line = msg.data[4:].decode()
				yield (stderr_or_stout, line)
			else:
				raise Exception('Unexpected reply type %s' % msg.command)
	
	async def __handle_socks_in(self, token:bytes, writer:asyncio.StreamWriter):
		try:
			while True:
				msg = await self.__channels[token].get()
				if msg.command != PSCMD.SOCKETDATA:
					break
				writer.write(msg.data)
				await writer.drain()
		finally:
			writer.close()
	
	async def __handle_tcp_client(self, reader:asyncio.StreamReader, writer:asyncio.StreamWriter):
		initcmd = None
		pt = None
		data = await reader.read(1)
		if data[0] == 5:
			authlen = await reader.read(1)
			authlen = authlen[0]
			methods = await reader.read(authlen)
			authmethods = []
			for c in methods:
				authmethods.append(SOCKS5Method(c))
			
			rep = SOCKS5NegoReply.construct(SOCKS5Method.NOAUTH)
			writer.write(rep.to_bytes())
			await writer.drain()

			resp = await SOCKS5Request.from_streamreader(reader)
			if resp.CMD in [SOCKS5Command.CONNECT, SOCKS5Command.BIND]:
				data = resp.CMD.value.to_bytes(4, byteorder='little', signed=False)
				data += resp.DST_PORT.to_bytes(4, byteorder='little', signed=False)
				data += str(resp.DST_ADDR).encode()
				initcmd = PSCMDMessage(PSCMD.SOCKETOPEN, data)
			else:
				raise NotImplementedError()
			
			token = await self.sendcmd(initcmd)
			msg = await self.__channels[token].get()
			if msg.command != PSCMD.CONTINUE:
				print('Failed to open socket on the remote end!')
				repl = SOCKS5Reply.construct(SOCKS5ReplyType.FAILURE, '', 0)
				writer.write(repl.to_bytes())
				await writer.drain()
				writer.close()
				return


			repl = SOCKS5Reply.construct(SOCKS5ReplyType.SUCCEEDED, '', 0)
			writer.write(repl.to_bytes())
			await writer.drain()
		elif data[0] == 4:
			raise NotImplementedError()
		else:
			raise ValueError() 
		
		try:
			pt = asyncio.create_task(self.__handle_socks_in(token, writer))
			self.__proxytasks.append(pt)
			while True:
				data = await reader.read(1590)
				if data == b'':
					#print('Client disconnected!')
					return
				msg = PSCMDMessage(PSCMD.SOCKETDATA, data, token=initcmd.token)
				await self.channel_data_out(msg.to_bytes())
		except Exception as e:
			print('Error! %s' % e)
			return
		finally:
			if pt is not None:
				pt.cancel()
			if initcmd is not None:
				msg = PSCMDMessage(PSCMD.OK, b'', token=initcmd.token)
				await self.channel_data_out(msg.to_bytes())

	async def socksproxy(self, listen_ip, listen_port):
		try:
			self.__socksserver = await asyncio.start_server(self.__handle_tcp_client, listen_ip, listen_port)
			print('SOCKS proxy started on %s:%s' % (listen_ip, listen_port))
			return True, None
		except Exception as e:
			return None, e