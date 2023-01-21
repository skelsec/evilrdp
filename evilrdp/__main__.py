
import sys

from aardwolf import logger
from aardwolf.commons.iosettings import RDPIOSettings
from aardwolf.commons.queuedata.constants import VIDEO_FORMAT
#from aardwolf.extensions.RDPEDYC.vchannels.socksoverrdp import SocksOverRDPChannel
from evilrdp._version import __banner__
from evilrdp.gui import EvilRDPGUI, RDPClientConsoleSettings
#from evilrdp.consolehelper import EVILRDPConsole
from PyQt5.QtWidgets import QApplication, qApp

def main():
	import logging
	import argparse
	parser = argparse.ArgumentParser(description='Async RDP Client. Duckyscript will be executed by pressing ESC 3 times')
	parser.add_argument('-v', '--verbose', action='count', default=0, help='Verbosity, can be stacked')
	parser.add_argument('--no-mouse-hover', action='store_false', help='Disables sending mouse hovering data. (saves bandwith)')
	parser.add_argument('--no-keyboard', action='store_false', help='Disables keyboard input. (whatever)')
	parser.add_argument('--res', default = '1024x768', help='Resolution in "WIDTHxHEIGHT" format. Default: "1024x768"')
	parser.add_argument('--keyboard', default = 'enus', help='Keyboard on the client side. Used for VNC and duckyscript')
	parser.add_argument('url', help="RDP connection url")

	args = parser.parse_args()

	if args.verbose == 1:
		logger.setLevel(logging.INFO)
	elif args.verbose == 2:
		logger.setLevel(logging.DEBUG)
	elif args.verbose > 2:
		logger.setLevel(1)

	width, height = args.res.upper().split('X')
	height = int(height)
	width = int(width)
	iosettings = RDPIOSettings()
	iosettings.video_width = width
	iosettings.video_height = height
	iosettings.video_out_format = VIDEO_FORMAT.QT5
	iosettings.client_keyboard = args.keyboard

	#from evilrdp.vchannels.pscmd import PSCMDChannel
	#iosettings.vchannels['PSCMD'] = PSCMDChannel('PSCMD')
	#from aardwolf.extensions.RDPEDYC.vchannels.socksoverrdp import SocksOverRDPChannel
	#iosettings.vchannels['PROXY'] = SocksOverRDPChannel(args.sockschannel, args.socksip, args.socksport)


	settings = RDPClientConsoleSettings(args.url, iosettings)
	settings.mhover = args.no_mouse_hover
	settings.keyboard = args.no_keyboard

	print(__banner__)

	app = QApplication(sys.argv)
	qtclient = EvilRDPGUI(settings)
	qtclient.show()
	app.exec_()
	qApp.quit()

if __name__ == '__main__':
	main()