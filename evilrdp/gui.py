import sys
import asyncio
import traceback
import queue
import threading
import time

from aardwolf import logger
from aardwolf.keyboard import VK_MODIFIERS
from aardwolf.commons.factory import RDPConnectionFactory
from aardwolf.commons.iosettings import RDPIOSettings
from aardwolf.commons.queuedata import RDPDATATYPE
from aardwolf.commons.queuedata.keyboard import RDP_KEYBOARD_SCANCODE, RDP_KEYBOARD_UNICODE
from aardwolf.commons.queuedata.mouse import RDP_MOUSE
from aardwolf.extensions.RDPECLIP.protocol.formatlist import CLIPBRD_FORMAT
from aardwolf.commons.queuedata.clipboard import RDP_CLIPBOARD_DATA_TXT
from aardwolf.commons.queuedata.constants import MOUSEBUTTON
from aardwolf.commons.target import RDPConnectionDialect

from evilrdp.consolehelper import EVILRDPConsole
from PIL.ImageQt import ImageQt


from PyQt5.QtWidgets import QApplication, QMainWindow, qApp, QLabel
from PyQt5.QtCore import QObject, pyqtSignal, pyqtSlot, QThread, Qt
from PyQt5.QtGui import QPainter, QImage, QPixmap

import pyperclip


# with the help of
# https://gist.github.com/jazzycamel/8abd37bf2d60cce6e01d

class RDPClientConsoleSettings:
	def __init__(self, url:str, iosettings:RDPIOSettings):
		self.mhover:int = True
		self.keyboard:int = True
		self.url:str = url
		self.iosettings:RDPIOSettings = iosettings
		# file path of the ducky file (if used)
		self.ducky_file = None
		# ducky script start delay, None means that typing will not start automatically
		self.ducky_autostart_delay = 5

class RDPImage:
	def __init__(self,x,y,image,width,height):
		self.x = x
		self.y = y
		self.image = image
		self.width = width
		self.height = height

class RDPInterfaceThread(QObject):
	result=pyqtSignal(RDPImage)
	connection_terminated=pyqtSignal()
	
	def __init__(self, parent=None, **kwargs):
		super().__init__(parent, **kwargs)
		self.settings:RDPClientConsoleSettings = None
		self.conn = None
		self.consoletask = None
		self.input_evt = None
		self.in_q = None
		self.loop_started_evt = threading.Event()
		self.gui_stopped_evt = threading.Event()
		self.input_handler_thread = None
		self.asyncthread:threading.Thread = None
	
	def set_settings(self, settings, in_q):
		self.settings = settings
		self.in_q = in_q

	def inputhandler(self, loop:asyncio.AbstractEventLoop):
		while not self.conn.disconnected_evt.is_set():
			data = self.in_q.get()
			loop.call_soon_threadsafe(self.conn.ext_in_queue.put_nowait, data)
			if data is None:
				break
		logger.debug('inputhandler terminating')

	async def ducky_keyboard_sender(self, scancode, is_pressed, as_char = False):
		### Callback function for the duckyexecutor to dispatch scancodes/characters to the remote end
		try:
			#print('SCANCODE: %s' % scancode)
			#print('is_pressed: %s' % is_pressed)
			#print('as_char: %s' % as_char)
			if as_char is False:
				ki = RDP_KEYBOARD_SCANCODE()
				ki.keyCode = scancode
				ki.is_pressed = is_pressed
				ki.modifiers = VK_MODIFIERS(0)
				await self.conn.ext_in_queue.put(ki)
			else:
				ki = RDP_KEYBOARD_UNICODE()
				ki.char = scancode
				ki.is_pressed = is_pressed
				await self.conn.ext_in_queue.put(ki)
		except Exception as e:
			traceback.print_exc()

	async def ducky_exec(self, bypass_delay = False):
		try:
			if self.settings.ducky_file is None:
				return
			from aardwolf.keyboard.layoutmanager import KeyboardLayoutManager
			from aardwolf.utils.ducky import DuckyExecutorBase, DuckyReaderFile
			if bypass_delay is False:
				if self.settings.ducky_autostart_delay is not None:
					await asyncio.sleep(self.settings.ducky_autostart_delay)
				else:
					return
			
			layout = KeyboardLayoutManager().get_layout_by_shortname(self.settings.iosettings.client_keyboard)
			executor = DuckyExecutorBase(layout, self.ducky_keyboard_sender, send_as_char = True if self.conn.target.dialect == RDPConnectionDialect.VNC else False)
			reader = DuckyReaderFile.from_file(self.settings.ducky_file, executor)
			await reader.parse()
		except Exception as e:
			traceback.print_exc()
	
	async def rdpconnection(self):
		input_handler_thread = None

		try:
			rdpurl = RDPConnectionFactory.from_url(self.settings.url, self.settings.iosettings)
			self.conn = rdpurl.get_connection(self.settings.iosettings)
			_, err = await self.conn.connect()
			if err is not None:
				raise err

			self.consoletask = asyncio.create_task(EVILRDPConsole(self.conn).run())
			#asyncio.create_task(self.inputhandler())
			input_handler_thread = asyncio.get_event_loop().run_in_executor(None, self.inputhandler, asyncio.get_event_loop())
			self.loop_started_evt.set()
			if self.settings.ducky_file is not None:
				x = asyncio.create_task(self.ducky_exec())
			while not self.gui_stopped_evt.is_set():
				data = await self.conn.ext_out_queue.get()
				if data is None:
					return
				if data.type == RDPDATATYPE.VIDEO:
					ri = RDPImage(data.x, data.y, data.data, data.width, data.height)
					if not self.gui_stopped_evt.is_set():
						self.result.emit(ri)
					else:
						return
				elif data.type == RDPDATATYPE.CLIPBOARD_READY:
					continue
				elif data.type == RDPDATATYPE.CLIPBOARD_NEW_DATA_AVAILABLE:
					continue
				elif data.type == RDPDATATYPE.CLIPBOARD_CONSUMED:
					continue
				elif data.type == RDPDATATYPE.CLIPBOARD_DATA_TXT:
					continue
				else:
					logger.debug('Unknown incoming data: %s'% data)

		except asyncio.CancelledError:
			return
		
		except Exception as e:
			traceback.print_exc()
		finally:
			if self.conn is not None:
				await self.conn.terminate()
			if input_handler_thread is not None:
				input_handler_thread.cancel()
			if not self.gui_stopped_evt.is_set():
				self.connection_terminated.emit()

	def starter(self):
		self.loop = asyncio.new_event_loop()
		asyncio.set_event_loop(self.loop)
		try:
			self.rdp_connection_task = self.loop.create_task(self.rdpconnection())
			self.loop.run_until_complete(self.rdp_connection_task)
			self.loop.close()
		except Exception as e:
			pass
			
	
	@pyqtSlot()
	def start(self):
		# creating separate thread for async otherwise this will not return
		# and then there will be no events sent back from application
		self.asyncthread = threading.Thread(target=self.starter, args=())
		self.asyncthread.start()
	
	@pyqtSlot()
	def stop(self):
		self.gui_stopped_evt.set()
		if self.conn is not None and self.loop.is_running():
			try:
				asyncio.run_coroutine_threadsafe(self.conn.terminate(), self.loop)
			except:
				pass
		time.sleep(0.1) # waiting connection to terminate
		self.rdp_connection_task.cancel()
		self.loop.stop()
	
	@pyqtSlot()
	def startducky(self):
		time.sleep(0.1) # waiting for keyboard flush
		asyncio.run_coroutine_threadsafe(self.ducky_exec(bypass_delay = True), self.loop)


class EvilRDPGUI(QMainWindow):
	#inputevent=pyqtSignal()

	def __init__(self, settings:RDPClientConsoleSettings):
		super().__init__()
		self.settings = settings
		self.ducky_key_ctr = 0

		# enabling this will singificantly increase the bandwith
		self.mhover = settings.mhover
		# enabling keyboard tracking
		self.keyboard = settings.keyboard
		self.is_rdp = True if settings.url.lower().startswith('rdp') is True else False

		# setting up the main window with the requested resolution
		self.setGeometry(0, 0, self.settings.iosettings.video_width, self.settings.iosettings.video_height)
		# this buffer will hold the current frame and will be contantly updated
		# as new rectangle info comes in from the server
		self._buffer = QImage(self.settings.iosettings.video_width, self.settings.iosettings.video_height, QImage.Format_RGB32)
		
		
		# setting up worker thread in a qthread
		# the worker recieves the video updates from the connection object
		# and then dispatches it to updateImage
		# this is needed as the RDPConnection class uses async queues
		# and QT is not async so an interface between the two worlds
		# had to be created
		self.in_q = queue.Queue()
		self._thread=QThread()
		self._threaded=RDPInterfaceThread(result=self.updateImage, connection_terminated=self.connectionClosed)
		self._threaded.set_settings(self.settings, self.in_q)
		self._thread.started.connect(self._threaded.start)
		self._threaded.moveToThread(self._thread)
		qApp.aboutToQuit.connect(self._thread.quit)
		self._thread.start()

		# setting up the canvas (qlabel) which will display the image data
		self._label_imageDisplay = QLabel()
		self._label_imageDisplay.setFixedSize(self.settings.iosettings.video_width, self.settings.iosettings.video_height)
		
		self.setCentralWidget(self._label_imageDisplay)
		
		# enabling mouse tracking
		self.setMouseTracking(True)
		self._label_imageDisplay.setMouseTracking(True)
		self.__extended_rdp_keys = {
			Qt.Key_End : 'VK_END', 
			Qt.Key_Down : 'VK_DOWN', 
			Qt.Key_PageDown : 'VK_NEXT', 
			Qt.Key_Insert : 'VK_INSERT', 
			Qt.Key_Delete : 'VK_DELETE', 
			Qt.Key_Print : 'VK_SNAPSHOT',
			Qt.Key_Home : 'VK_HOME', 
			Qt.Key_Up : 'VK_UP', 
			Qt.Key_PageUp : 'VK_PRIOR', 
			Qt.Key_Left : 'VK_LEFT',
			Qt.Key_Right : 'VK_RIGHT',
			Qt.Key_Meta : 'VK_LWIN',
			Qt.Key_Enter : 'VK_RETURN',
			Qt.Key_Menu : 'VK_LMENU',
			Qt.Key_Pause : 'VK_PAUSE',
			Qt.Key_Slash: 'VK_DIVIDE',
			Qt.Key_Period: 'VK_DECIMAL',

			#Qt.Key_Shift: 'VK_LSHIFT',
			#Qt.Key_Tab: 'VK_TAB',
			#Qt.Key_0 : 'VK_NUMPAD0',
			#Qt.Key_1 : 'VK_NUMPAD1',
			#Qt.Key_2 : 'VK_NUMPAD2',
			#Qt.Key_3 : 'VK_NUMPAD3',
			#Qt.Key_4 : 'VK_NUMPAD4',
			#Qt.Key_5 : 'VK_NUMPAD5',
			#Qt.Key_6 : 'VK_NUMPAD6',
			#Qt.Key_7 : 'VK_NUMPAD7',
			#Qt.Key_8 : 'VK_NUMPAD8',
			#Qt.Key_9 : 'VK_NUMPAD9',
		}

		self.__qtbutton_to_rdp = {
			Qt.LeftButton   : MOUSEBUTTON.MOUSEBUTTON_LEFT,
			Qt.RightButton  : MOUSEBUTTON.MOUSEBUTTON_RIGHT,
			Qt.MidButton    : MOUSEBUTTON.MOUSEBUTTON_MIDDLE,
			Qt.ExtraButton1 : MOUSEBUTTON.MOUSEBUTTON_5,
			Qt.ExtraButton2 : MOUSEBUTTON.MOUSEBUTTON_6,
			Qt.ExtraButton3 : MOUSEBUTTON.MOUSEBUTTON_7,
			Qt.ExtraButton4 : MOUSEBUTTON.MOUSEBUTTON_8,
			Qt.ExtraButton5 : MOUSEBUTTON.MOUSEBUTTON_9,
			Qt.ExtraButton6 : MOUSEBUTTON.MOUSEBUTTON_10,
		}
	
	def closeEvent(self, event):
		self.connectionClosed()
		event.accept()
	
	def connectionClosed(self):
		self.in_q.put(None)
		self._threaded.stop()
		self._thread.quit()
		self.close()
	
	def updateImage(self, event):
		rect = ImageQt(event.image)
		if event.width == self.settings.iosettings.video_width and event.height == self.settings.iosettings.video_height:
			self._buffer = rect
		else:
			with QPainter(self._buffer) as qp:
				qp.drawImage(event.x, event.y, rect, 0, 0, event.width, event.height)
		
		pixmap01 = QPixmap.fromImage(self._buffer)
		pixmap_image = QPixmap(pixmap01)
		self._label_imageDisplay.setPixmap(pixmap_image)
		self._label_imageDisplay.setAlignment(Qt.AlignCenter)
		self._label_imageDisplay.setScaledContents(True)
		self._label_imageDisplay.setMinimumSize(1,1)
		self._label_imageDisplay.show()
	
	## this is for testing!
	#def keyevent_to_string(self, event):
	#	keymap = {}
	#	for key, value in vars(Qt).items():
	#		if isinstance(value, Qt.Key):
	#			keymap[value] = key.partition('_')[2]
	#	modmap = {
	#		Qt.ControlModifier: keymap[Qt.Key_Control],
	#		Qt.AltModifier: keymap[Qt.Key_Alt],
	#		Qt.ShiftModifier: keymap[Qt.Key_Shift],
	#		Qt.MetaModifier: keymap[Qt.Key_Meta],
	#		Qt.GroupSwitchModifier: keymap[Qt.Key_AltGr],
	#		Qt.KeypadModifier: keymap[Qt.Key_NumLock],
	#		}
	#	sequence = []
	#	for modifier, text in modmap.items():
	#		if event.modifiers() & modifier:
	#			sequence.append(text)
	#	key = keymap.get(event.key(), event.text())
	#	if key not in sequence:
	#		sequence.append(key)
	#	return '+'.join(sequence)

	def send_key(self, e, is_pressed):
		# https://doc.qt.io/qt-5/qt.html#Key-enum
		
		# ducky script starter
		if is_pressed is True:
			if e.key()==Qt.Key_Escape:
				self.ducky_key_ctr += 1
				if self.ducky_key_ctr == 3:
					self.ducky_key_ctr = 0
					self._threaded.startducky()
			else:
				self.ducky_key_ctr = 0

		if self.keyboard is False:
			return
		#print(self.keyevent_to_string(e))

		if e.key()==(Qt.Key_Control and Qt.Key_V):
			ki = RDP_CLIPBOARD_DATA_TXT()
			ki.datatype = CLIPBRD_FORMAT.CF_UNICODETEXT
			ki.data = pyperclip.paste()
			self.in_q.put(ki)
		
		modifiers = VK_MODIFIERS(0)
		qt_modifiers = QApplication.keyboardModifiers()
		if bool(qt_modifiers & Qt.ShiftModifier) is True and e.key() != Qt.Key_Shift:
			modifiers |= VK_MODIFIERS.VK_SHIFT
		if bool(qt_modifiers & Qt.ControlModifier) is True and e.key() != Qt.Key_Control:
			modifiers |= VK_MODIFIERS.VK_CONTROL
		if bool(qt_modifiers & Qt.AltModifier) is True and e.key() != Qt.Key_Alt:
			modifiers |= VK_MODIFIERS.VK_MENU
		if bool(qt_modifiers & Qt.KeypadModifier) is True and e.key() != Qt.Key_NumLock:
			modifiers |= VK_MODIFIERS.VK_NUMLOCK
		if bool(qt_modifiers & Qt.MetaModifier) is True and e.key() != Qt.Key_Meta:
			modifiers |= VK_MODIFIERS.VK_WIN

		ki = RDP_KEYBOARD_SCANCODE()
		ki.keyCode = e.nativeScanCode()
		ki.is_pressed = is_pressed
		if sys.platform == "linux":
			#why tho?
			ki.keyCode -= 8
		ki.modifiers = modifiers

		if e.key() in self.__extended_rdp_keys.keys():
			ki.vk_code = self.__extended_rdp_keys[e.key()]

		#print('SCANCODE: %s' % ki.keyCode)
		#print('VK CODE : %s' % ki.vk_code)
		#print('TEXT    : %s' % repr(e.text()))
		self.in_q.put(ki)

	def send_mouse(self, e, is_pressed, is_hover = False):
		if is_hover is True and self.settings.mhover is False:
			# is hovering is disabled we return immediately
			return
		buttonNumber = MOUSEBUTTON.MOUSEBUTTON_HOVER
		if is_hover is False:
			buttonNumber = self.__qtbutton_to_rdp[e.button()]

		mi = RDP_MOUSE()
		mi.xPos = e.pos().x()
		mi.yPos = e.pos().y()
		mi.button = buttonNumber
		mi.is_pressed = is_pressed if is_hover is False else False

		self.in_q.put(mi)
	
	def keyPressEvent(self, e):
		self.send_key(e, True)

	def keyReleaseEvent(self, e):
		self.send_key(e, False)
	
	def mouseMoveEvent(self, e):
		self.send_mouse(e, False, True)

	def mouseReleaseEvent(self, e):
		self.send_mouse(e, False)

	def mousePressEvent(self, e):
		self.send_mouse(e, True)
	
