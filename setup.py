#!/usr/bin/env python

# Copyright (c) 2019 Red Hat, Inc.
# All Rights Reserved.

from setuptools import setup, find_packages

with open('README.md', 'r') as f:
    long_description = f.read()

setup(
    name="receptor",
    version="0.6.1",
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
