#!/usr/bin/env python3

import argparse
import requests
import os.path
import os
import re
import subprocess
import json
import hashlib

from shutil import copy as copy_file

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
            "make,mk": 'make [CHANGED/all/[name]] files',
            "new": 'create a new lyrics sheet from a template',
            'ed,vim': 'edit file',
            "status": 'print list of changed files',
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
parser.add_argument("-e", "--editor", default="code", help="set editor")

args = parser.parse_args()
src = args.src
src_root = args.src
out = args.out
conf_dir = args.conf
editor = args.editor

prompt_style = Style.from_dict({'prompt': 'bg:ansiyellow fg:ansiblack', 
                                'path': 'fg:ansiblue bg:ansiblack', 
                                'arrowr': 'fg:ansired', 
                                'arrowl1': 'fg:ansiyellow bg:ansiblack', 
                                'arrowl2': 'fg:ansiblack bg:', 
                                'right': 'fg:ansiwhite bg:ansired'})

def message(stat, msg):
    status = {'n': '\033[36mNW\033[0m', 
              'c': '\033[36mCH\033[0m', 
              'e': '\033[31mER\033[0m', 
              'o': '\033[32mOK\033[0m'}
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

def get_changed_files():
    out = []
    hashes = dict()
    with open(os.path.join(conf_dir,"hashes.json"), 'r') as js:
        hashes = json.load(js)
    # count changed and untracked files
    for root, _, files in os.walk(src):
        for name in files:
            if name.endswith(".md") and not name == "README.md":
                filename = os.path.join(os.path.relpath(root,src_root), name)
                if filename.startswith('./'):
                    filename = filename[2:]
                
                if filename not in hashes:
                    out.append((filename,'new'))
                elif hashes[filename] != sha256(os.path.join(src_root,filename)):
                    out.append((filename,'changed'))
    return out

def get_rprompt():
    count = len(get_changed_files())
    if count > 0:
        return [('class:arrowr', '\ue0b2'), ('class:right', "  {}".format(count))]

def get_relpath(path,pre=""):
    out = os.path.relpath(path, src_root)
    if out.startswith('./'):
        out = out[2:]
    elif out == '.':
        out = ""
    return pre + out

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
            relpath = get_relpath(src,pre="/")
            prompt_message = [('class:prompt', ' lyrium '), ('class:arrowl1', '\ue0b0'), ('class:path', " {} ".format(relpath)), ('class:arrowl2', '\ue0b0 ')]
            cmd = prompt(prompt_message,
                            history=FileHistory(os.path.join(conf_dir, 'lyr.history')),
                            auto_suggest=AutoSuggestFromHistory(),
                            completer=completer,
                            rprompt=get_rprompt,
                            style=prompt_style)
        
        # print(cmd)
        # parse command
        if cmd.startswith("..") and cmd.replace(".",'') == "":
            l = len(cmd) - 1
            p = "../"*l
            cmd = "cd " + p

        try:
            cmd,args = cmd.split(' ', 1)
        except ValueError:
            args = ''

        if cmd == "q":
            break
        elif cmd == "src" or cmd == "cd":
            if args == '/' or args == '':
                src = src_root

            else:
                target = os.path.normpath(os.path.join(src,args))
                if not os.path.isdir(target):
                    message('e', "not a valid directory name")
                    continue
                # stay inside the given root
                if os.path.samefile(os.path.commonpath([target,src_root]), src_root):
                    src = target
                else:
                    message("e", "leaving the root is not allowed")

        elif cmd in src_files:
            lyr_command = build_lyr_command(md(cmd), args)
            # print(lyr_command)
            subprocess.call(lyr_command, shell=True)
            if not " -p" in lyr_command:
                input()

        elif cmd in ["l", 'la', 'ls']: #TODO: two column mode for files and folders?
            for x in src_files:
                if os.path.isdir(os.path.join(src,x)):
                    print("\033[34m{}\033[0m".format(x))
                elif os.path.isfile(os.path.join(src,md(x))):
                    print("\033[32m{}\033[0m".format(x))
                else:
                    print("\033[31m{}\033[0m".format(x))

        elif cmd in ["h", "?", "help"]:
            for k,v in COMMANDS.items():
                print("{}\t{}".format(k,v))

        elif cmd == 'pdf':
            pdf_name = os.path.join(out,get_relpath(src),pdf(args))
            subprocess.call("atril -s {}".format(pdf_name),shell=True)

        elif cmd in ['make', 'mk']:
            tmp_src = src
            collection = []
            hashes = dict()
            with open(os.path.join(conf_dir,"hashes.json"), 'r') as js:
                hashes = json.load(js)
            if args == '':
                src = src_root
                # collect changed and untracked files
                for root, _, files in os.walk(src):
                    for name in files:
                        if name.endswith(".md") and not name == "README.md":
                            filename = os.path.join(get_relpath(root), name)
                            
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
                            filename = os.path.join(os.path.relpath(root,src), name)#TODO: careful filename handling
                            if filename.startswith('./'):
                                filename = filename[2:]
                            collection.append(filename)
            else:
                # collect only files matching args.split()
                for arg in args.split(" "):
                    if os.path.isfile(os.path.join(src,md(arg))):
                        collection.append(md(arg))
            #make
            if len(collection) == 0:
                message('e', 'no files selected')
            
            for filename in collection:
                lyr_command = build_lyr_command(filename, "-p")
                subprocess.call(lyr_command, shell=True)
                message("o", filename)
                rel_filename = get_relpath(os.path.join(src,filename))
                hashes[rel_filename] = sha256(os.path.join(src,filename))

            if args == '':
                src = tmp_src

            # update hashes
            with open(os.path.join(conf_dir,"hashes.json"), 'w') as js:
                json.dump(hashes,js,indent=4)

        elif cmd == 'new':
            name = os.path.join(src,md(args).replace(' ','_'))
            p = copy_file(os.path.join(conf_dir,'template.md'),name)
            txt = name[:-2] + "txt"
            if os.path.isfile(txt) and os.path.getsize(txt) == 0:
                os.remove(txt)
                message("o", txt + ' removed')
            message('o', p + ' created')
            subprocess.call('{} {}'.format(editor,name), shell=True)

        elif cmd in ['ed', 'edit', 'vi', 'vim', 'code']:
            subprocess.call('{} {}'.format(editor,os.path.join(src,md(args))), shell=True)

        elif cmd == "status":
            for x in get_changed_files():
                if x[1] == 'new':
                    message('n', x[0])
                elif x[1] == 'changed':
                    message('c', x[0])
                else:
                    print(x)

        elif cmd != '':
            message('e', "unknown command")



    except KeyboardInterrupt:
        continue
    except EOFError:
        exit(0)