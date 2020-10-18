#!/usr/bin/env python3
#
# Copyright (c) 2020 Tatu Ylonen.  See LICENSE and https://ylonen.org

from setuptools import setup

with open("README.md", "r") as f:
    long_description = f.read()

setup(name="wikitextprocessor",
      version="0.0.3",
      description="Parser and expander for Wikipedia, Wiktionary etc. dump files, with Lua execution support",
      long_description=long_description,
      long_description_content_type="text/markdown",
      author="Tatu Ylonen",
      author_email="ylo@clausal.com",
      url="https://ylonen.org",
      license="MIT (some included files have other free licences)",
      download_url="https://github.com/tatuylonen/wikitextprocessor",
      scripts=[],
      packages=["wikitextprocessor"],
      package_data={"wikitextprocessor": ["lua"]},
      install_requires=[],
      classifiers=[
          "Development Status :: 3 - Alpha",
          "Intended Audience :: Developers",
          "Intended Audience :: Science/Research",
          "License :: OSI Approved :: MIT License",
          "Natural Language :: English",
          "Operating System :: POSIX :: Linux",
          "Programming Language :: Python",
          "Programming Language :: Python :: 3 :: Only",
          "Topic :: Text Processing",
          "Topic :: Text Processing :: Linguistic",
          ])
