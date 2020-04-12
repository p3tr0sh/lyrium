#!/usr/bin/env python3

import argparse
import requests
import os.path
import os
import re
import subprocess
import json
import hashlib


from prompt_toolkit import prompt
from prompt_toolkit.history import FileHistory
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.completion import WordCompleter
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.styles import Style

# metadata in json file for searching 

COMMANDS = {"src,cd": 'set source folder',
            "out": 'set output folder',
            "l,ls,la": 'list files and folders',
            "pdf": 'show pdf',
            "make": 'make [CHANGED/all/[name]] files',
            "q": 'quit',
            "h,?": 'help'}

COMMAND_KEYS = []
for key in COMMANDS.keys():
    for item in key.split(','):
        COMMAND_KEYS.append(item)
COMMAND_KEYS.sort()

parser = argparse.ArgumentParser()
parser.add_argument("-s", "--src", default=os.getcwd(), help="define source root folder")
parser.add_argument("-o", "--out", default=os.getcwd(), help="define output root folder")
parser.add_argument("-c", "--conf", default=os.getcwd(), help="define config folder")

args = parser.parse_args()
src = args.src
src_root = args.src
out = args.out
conf_dir = args.conf

def message(stat, msg):
    status = {'n': '\033[36mNEW\033[0m', 
              'c': '\033[36mCHANGE\033[0m', 
              'e': '\033[31mERROR\033[0m', 
              'd': '\033[32mDONE\033[0m'}
    print("[ {:>{wid}} ] {}".format(status[stat],msg,wid=max([len(l) for l in status.values()])))

def md(filename):
    return "{}.md".format(filename)

def pdf(filename):
    return "{}.pdf".format(filename)

def filter_suggestions(file_list):
    output = []
    if os.path.samefile(os.path.commonpath([src,src_root]), src_root) and not os.path.samefile(src, src_root):
        output.append("..")
    for f in file_list:

        if os.path.isdir(os.path.join(src,f)):
            output.append(f)
        elif f.endswith(".md"):
            output.append(f[:-3])
    return sorted(output)

def build_lyr_command(filename, args):
    dirname = os.path.split(filename)[0]
    md_file = os.path.join(src,filename)
    md_args = ""
    with open(md_file) as md:
        md_args = md.readline()
        if md_args.startswith('#!/bin/lyr'):
            md_args = md_args[11:].replace('\n','')
    # smuggle in the default out option as first argument to allow overriding later on
    md_args = "-o {} {}".format(os.path.normpath(os.path.join(out,os.path.relpath(src,src_root),dirname)), md_args)
    lyr_command = "/bin/lyr {} {} {}".format(md_file,md_args,args)
    return lyr_command

def sha256(filename):
    h = hashlib.sha256()
    with open(filename, 'rb') as f:
        while True:
            chunk = f.read(h.block_size)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()

while True:
    try:
        with patch_stdout():
            # generate file completion
            # print(src)
            src_files = os.listdir(src)
            try:
                src_files.remove("README.md")
                src_files.remove(".git")
            except ValueError:
                pass
            src_files = filter_suggestions(src_files)
            # print(src_files)
            completer = WordCompleter(COMMAND_KEYS + src_files)
            relpath = os.path.relpath(src,src_root)
            relpath = "/" if relpath == "." else "/{}".format(relpath)
            prompt_message = [('class:prompt', 'lyrium:'), ('class:path', relpath), ('class:prompt', ' > ')]
            cmd = prompt(prompt_message,
                            history=FileHistory(os.path.join(conf_dir, 'lyr.history')),
                            auto_suggest=AutoSuggestFromHistory(),
                            completer=completer,
                            style=Style.from_dict({'prompt': 'fg:ansiyellow', 'path': 'fg:ansiblue'}))
        
        # print(cmd)
        # parse command
        if cmd == "..":
            cmd = "cd .."

        try:
            cmd,args = cmd.split(' ', 1)
        except ValueError:
            args = ''

        if cmd == "q":
            break
        if cmd == "src" or cmd == "cd":
            if args == '/' or args == '':
                src = src_root

            else:
                target = os.path.normpath(os.path.join(src,args))
                if not os.path.isdir(target):
                    # print("[ ERRO ] not a valid directory name")
                    message('e', "not a valid directory name")
                    continue
                # stay inside the given root
                if os.path.samefile(os.path.commonpath([target,src_root]), src_root):
                    src = target
                else:
                    message("e", "leaving the root is not allowed")

        if cmd in src_files:
            lyr_command = build_lyr_command(md(cmd), args)
            # print(lyr_command)
            subprocess.call(lyr_command, shell=True)
            if not " -p" in lyr_command:
                input()

        if cmd in ["l", 'la', 'ls']:
            for x in src_files:
                if os.path.isdir(os.path.join(src,x)):
                    print("\033[34m{}\033[0m".format(x))
                elif os.path.isfile(os.path.join(src,md(x))):
                    print("\033[32m{}\033[0m".format(x))
                else:
                    print("\033[31m{}\033[0m".format(x))

        if cmd in ["h", "?", "help"]:
            for k,v in COMMANDS.items():
                print("{}\t{}".format(k,v))

        if cmd == 'pdf':
            pdf_name = os.path.join(out,os.path.relpath(src,src_root),pdf(args))
            subprocess.call("atril -s {}".format(pdf_name),shell=True)

        if cmd == 'make':
            collection = []
            hashes = dict()
            with open(os.path.join(conf_dir,"hashes.json"), 'r') as js:
                hashes = json.load(js)
            if args == '':
                # collect changed and untracked files
                for root, _, files in os.walk(src):
                    for name in files:
                        if name.endswith(".md") and not name == "README.md":
                            filename = os.path.join(os.path.relpath(root,src_root), name)
                            if filename.startswith('./'):
                                filename = filename[2:]
                            
                            if filename not in hashes:
                                message("n", filename)
                                collection.append(filename)
                            elif hashes[filename] != sha256(os.path.join(src_root,filename)):
                                message("c", filename)
                                collection.append(filename)
            elif args == 'all':
                # collect all files under the current root
                for root, _, files in os.walk(src):
                    for name in files:
                        if name.endswith(".md") and not name == "README.md":
                            filename = os.path.join(os.path.relpath(root,src), name)
                            if filename.startswith('./'):
                                filename = filename[2:]
                            collection.append(filename)
            else:
                # collect only files matching args.split()
                for arg in args.split(" "):
                    if os.path.isfile(os.path.join(src,md(arg))):
                        collection.append(md(arg))
            #make
            for filename in collection:
                lyr_command = build_lyr_command(filename, "-p")
                subprocess.call(lyr_command, shell=True)
                message("d", filename)
                hashes[filename] = sha256(os.path.join(src,filename))

            # update hashes
            with open(os.path.join(conf_dir,"hashes.json"), 'w') as js:
                json.dump(hashes,js,indent=4)




    except KeyboardInterrupt:
        continue
    except EOFError:
        exit(0)