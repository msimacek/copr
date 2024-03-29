#!/usr/bin/python

from setuptools import setup

import sys

long_description = """Copr is designed to be a lightweight buildsystem that allows contributors
to create packages, put them in repositories, and make it easy for users
to install the packages onto their system. Within the Fedora Project it
is used to allow packagers to create third party repositories.

This part is a command line interface to use copr."""

from copr_cli.main import __description__, __version__

requires = [
    'copr'
]


__name__ = 'copr-cli'
__version__ = __version__
__description__ = __description__
__author__ = "Pierre-Yves Chibon"
__author_email__ = "pingou@pingoured.fr"
__url__ = "http://fedorahosted.org/copr/"


setup(
    name=__name__,
    version=__version__,
    description=__description__,
    long_description=long_description,
    author=__author__,
    author_email=__author_email__,
    url=__url__,
    license='GPLv2+',
    classifiers=[
        "License :: OSI Approved :: GNU General Public License v2 or later (GPLv2+)",
        "Programming Language :: Python :: 2",
        "Programming Language :: Python :: 2.7",
        "Topic :: System :: Archiving :: Packaging",
        "Development Status :: 1 - Alpha",
    ],
    install_requires=requires,
    packages=['copr_cli'],
    namespace_packages=['copr_cli'],
    include_package_data=True,
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'copr-cli = copr_cli.main:main'
        ]
    },
)
