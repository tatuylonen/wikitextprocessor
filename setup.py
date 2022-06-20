#!/usr/bin/env python3
#
# Copyright (c) 2020-2021 Tatu Ylonen.  See LICENSE and https://ylonen.org

from setuptools import setup

with open("README.md", "r") as f:
    long_description = f.read()

setup(name="wikitextprocessor",
      version="0.4.96",
      description="Parser and expander for Wikipedia, Wiktionary etc. dump files, with Lua execution support",
      long_description=long_description,
      long_description_content_type="text/markdown",
      author="Tatu Ylonen",
      author_email="ylo@clausal.com",
      url="https://github.com/tatuylonen/wikitextprocessor",
      license="MIT (some included files have other free licences)",
      download_url="https://github.com/tatuylonen/wikitextprocessor",
      scripts=[],
      packages=["wikitextprocessor"],
      package_data={"wikitextprocessor":
                    ["lua/*.lua",
                     "lua/mediawiki-extensions-Scribunto/COPYING",
                     "lua/mediawiki-extensions-Scribunto/includes/engines/LuaCommon/lualib/*.lua",
                     "lua/mediawiki-extensions-Scribunto/includes/engines/LuaCommon/lualib/ustring/*.lua",
                     "lua/mediawiki-extensions-Scribunto/includes/engines/LuaCommon/lualib/luabit/*.lua"]},
      install_requires=["lupa", "dateparser", "lru-dict"],
      keywords=[
          "dictionary",
          "wiktionary",
          "wikipedia",
          "data extraction",
          "wikitext",
          "scribunto",
          "lua",
      ],
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
