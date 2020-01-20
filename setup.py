#!/usr/bin/env python

# Copyright (c) 2019 Red Hat, Inc.
# All Rights Reserved.

from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name="receptor",
    version="0.1.0",
    author='Red Hat',
    url="https://github.com/project-receptor/receptor",
    license='Apache',
    packages=find_packages(),
    long_description=long_description,
    long_description_content_type='text/markdown',
    python_requires=">=3.6",
    install_requires=[
        "prometheus_client==0.7.1",
        "aiohttp==3.6.2",
        "python-dateutil>=2.8.1",
    ],
    extras_require={
        'dev': [
            'attrs~=19.3.0',
            'click~=7.0',
            'flake8~=3.7.9',
            'pylint~=2.4.4',
            'pyparsing~=2.4.5',
            'pytest~=5.3.2',
            'pytest-asyncio~=0.10.0',
            'pyyaml~=5.2',
            'requests~=2.22.0',
            'wait-for~=1.1.1',
        ],
    },
    zip_safe=False,
    entry_points={
        'console_scripts': [
            'receptor = receptor.__main__:main'
        ]
    },
    classifiers=[
        "Programming Language :: Python :: 3",
    ],
)
