from setuptools import setup, find_packages
from distutils.core import setup, Extension
import re
import platform

VERSIONFILE="evilrdp/_version.py"
verstrline = open(VERSIONFILE, "rt").read()
VSRE = r"^__version__ = ['\"]([^'\"]*)['\"]"
mo = re.search(VSRE, verstrline, re.M)
if mo:
    verstr = mo.group(1)
else:
    raise RuntimeError("Unable to find version string in %s." % (VERSIONFILE,))

setup(
	# Application name:
	name="evilrdp",

	# Version number (initial):
	version=verstr,

	# Application author details:
	author="Tamas Jos",
	author_email="info@skelsecprojects.com",

	# Packages
	packages=find_packages(),

	# Include additional files into the package
	include_package_data=True,


	# Details
	url="https://github.com/skelsec/evilrdp",

	zip_safe = False,
	#
	# license="LICENSE.txt",
	description="evilrdp",

	# long_description=open("README.txt").read(),
	python_requires='>=3.7',

	install_requires=[
		'prompt-toolkit',
		'aardwolf>=0.2.5',
		'pyqt5',
		'pyqt5-sip',
		'pyperclip',
	],
	
	
	classifiers=[
		"Programming Language :: Python :: 3.8",
		"Operating System :: OS Independent",
	],
	entry_points={
		'console_scripts': [
			'evilrdp = evilrdp.evilrdp:main',
		],

	}
)
