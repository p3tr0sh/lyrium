#!/usr/bin/env python3

from lxml import html
import argparse
import requests
import os.path
import os
import re

import subprocess

# parse md files
# 1. line: # Title
# 2. line: ## Artist
# 3. line: ### Key (+ shift)
# ---
# body

class Chord:
    SHARP = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
    FLAT  = ("C", "Db", "D", "Eb", "E", "F", "Gb", "G", "Ab", "A", "Bb", "B")

    def __init__(self, symbol):
        self.parse(symbol)

    def parse(self, symbol):
        self.third = not symbol[0].islower()
        symbol = symbol[0].upper() + symbol[1:]
        if symbol[0] == "H":
            symbol[0] = "B"
        if len(symbol) >= 2 and (symbol[:2] in Chord.SHARP or symbol[:2] in Chord.FLAT): #TODO: zu ungenau, basston
            self.base = symbol[:2]
            self.addition = symbol[2:]
        else:
            self.base = symbol[0]
            self.addition = symbol[1:]
    
    def transpose(self, amount):
        if amount == 0:
            return self
        try:
            idx = self.index()
        except ValueError:
            return self
        if amount < 0:
            self.base = Chord.FLAT[(idx + amount) % 12]
            if '/' in self.addition:
                left, right = self.addition.split('/',1)
                self.addition = '{}/{}'.format(left,str(Chord(right).transpose(amount)))
        else:
            self.base = Chord.SHARP[(idx + amount) % 12]
            if '/' in self.addition:
                left, right = self.addition.split('/',1)
                self.addition = '{}/{}'.format(left,str(Chord(right).transpose(amount)))
        return self

    def index(self):
        return Chord.FLAT.index(self.base) if self.base in Chord.FLAT else Chord.SHARP.index(self.base)
    
    def __str__(self):
        s = self.base if self.third else self.base.lower()
        return s + self.addition

    def distance(self, symbol): # TODO: only upwards shift compatible
        idx = self.index()
        idx_symbol = Chord(symbol).index()
        print(self.base, idx, symbol, idx_symbol)
        return (idx_symbol - idx) % 12

key_shift = 0

parser = argparse.ArgumentParser()
parser.add_argument("file")
key_group = parser.add_mutually_exclusive_group()
key_group.add_argument("-n", "--no-chords", action="store_true")
key_group.add_argument("-t", "--transposed", action="store_true")
key_group.add_argument("-T", "--transpose", help="shift in half tone steps or to another key")
parser.add_argument("-C", "--no-color", action="store_true", help="disable color output of chords")
parser.add_argument("-s", "--sheet", action="store_true", help="only print the sheet")
parser.add_argument("-p", "--pdf", action="store_true", help="instead of printing to stdout, create pdf file")
parser.add_argument("-c", "--pdf-columns", type=int, choices=[1,2,3], default=2, help="define the number of columns in pdf mode, default: 2")
parser.add_argument("-o", "--output-folder", default="./", help="if in pdf mode define the output folder, default is ./")
parser.add_argument("-l", "--lyrics", action="store_true", help="only print the lyrics")
parser.add_argument("-v", "--verbose", action="store_true", help="add verbosity")

args = parser.parse_args()

if args.pdf:
    args.no_color = True


def match_after(expr, target):
    return re.search(expr, target, re.MULTILINE)[0]

def out(text):
    
    ischord = False
    output = ""
    chordline = ""
    lyrline = ""
    chordlength = 0

    linecount = 0
    parts_start_at = [] # collect line numbers of empty lines for possible split points

    # color option
    color = ["",""]
    if not args.no_color:
        color[0] = "\033[1;35m"
        color[1] = "\033[0;0m"

    if args.pdf:
        color[0] = "\\textcolor{red}{"
        color[1] = "}"
        output += "\\begin{minipage}{\\linewidth}\n"
        output += "\\begin{Verbatim}[commandchars=\\\\\\{\\}]\n"
    
    for line in text.splitlines():
        if not line.startswith('|'):
            for c in line: # look for chords and separate them into additional lines
                if c == "[":
                    ischord = True
                elif c == "]":
                    ischord = False
                    chordline += " "
                    chordlength += 1
                elif ischord:
                    chordline += c
                    chordlength += 1
                else:
                    if chordlength == 0:
                        chordline += " "
                    else:
                        if c == " ":
                            chordlength -= 1
                            while chordlength > 0:
                                lyrline += " "
                                chordlength -= 1
                        else:
                            chordlength -= 1
                    lyrline += c
        else:
            chordline = line.replace('[','').replace(']','')

        if line == '': # empty line, allow page break here
            if args.pdf:
                output += "\n"
                output += "\\end{Verbatim}\n"
                output += "\\end{minipage}\n"
                output += "\\begin{minipage}{\\linewidth}\n"
                output += "\\begin{Verbatim}[commandchars=\\\\\\{\\}]\n"
            parts_start_at.append(linecount)
        
        if chordline.rstrip() != "" and not args.lyrics:
            output += color[0] + chordline + color[1] + "\n"
            linecount += 1
        if not (chordline.rstrip() != "" and lyrline.rstrip() == ""):
            output += lyrline + "\n"
            linecount += 1
        chordline = ""
        lyrline = ""
        chordlength = 0
    
    if args.pdf:
        output += "\\end{Verbatim}\n"
        output += "\\end{minipage}\n"

    # wrap text if in terminal mode and more than $lines have to be printed
    colwidth = int(os.get_terminal_size()[0]/2)
    if linecount + 3 > os.get_terminal_size()[1] and not args.pdf:
        # find the right spot to split into columns
        idx = linecount
        for part in parts_start_at:
            if part > linecount/2:
                idx = part
                break

        # split
        splitted = output.split('\n')
        left = splitted[:idx]
        right = splitted[idx:]

        # append empty strings to the shorter list
        if len(left) > len(right):
            right += ['']*(len(left)-len(right))
        else:
            left += ['']*(len(right)-len(left))
        output_2 = ""

        # build string
        for x,y in zip(left,right):
            offset = 0 # coloring lines yields a negative offset to the line width, which has to be countered
            if color[0] in x:
                offset = len(color[0]) + len(color[1])
            output_2 += "{:{wid}s}|  {}\n".format(x,y,wid=colwidth+offset)
        return output_2[:-1]
    return output[:-1]


# sheet mode
def sheet(text):

    parts = []
    for line in text.splitlines():
        if len(line) == 0:
            continue
        if line[0] == '>':
            parts.append(line[2:].split(" ; ")) # split on ; to allow chord progression with '|'
            parts[-1].append([])
        elif not args.sheet:
            for o in out(line)[:-1].split('\n'):
                parts[-1][-1].append(o)
    width1 = max([len(x[0]) for x in parts])
    width2 = max([len(x[1]) for x in parts])

    # color option
    color = ["",""]
    if not args.no_color:
        color[0] = "\033[2m"
        color[1] = "\033[0;0m"

    output = ""
    for p in parts:
        output += "{:{w1}s} | {:>{w2}s} | ".format(p[0],p[1],w1=width1,w2=width2)
        if type(p[2]) is str:
            output += "{}{}{}\n".format(color[0],p[2],color[1])
        else:
            try:
                output += "{}\n".format(p[-1].pop(0))
            except IndexError:
                output += "\n"
        
        for x in p[-1]:
            output += "{:{w1}s} | {:>{w2}s} | {}\n".format("","",x,w1=width1,w2=width2)
    return output

def sanitize(string):
    return string.replace("#","\\#").replace("&", "\\&").replace("'","{\\textquotesingle}")

def pdf(body,title,artist,key):
    artist = sanitize(artist)
    title = sanitize(title)
    key = sanitize(key)
    landscape = ",landscape"
    if args.pdf_columns == 1:
        landscape = ""
    tex = "\\documentclass[notitlepage,10pt" + landscape + "]{extarticle}\n"
    tex += "\\usepackage[a4paper,margin=0.6in" + landscape + "]{geometry}\n"
    tex += "\\usepackage{fontspec}\n"
    tex += "\\usepackage{tabularx}\n"
    tex += "\\usepackage{array}\n"
    tex += "\\usepackage{multicol}\n"
    tex += "\\usepackage{xcolor}\n"
    tex += "\\usepackage{fancyvrb}\n"
    tex += "\\setmainfont[Ligatures=TeX]{MuseJazzText}\n"
    tex += "\\newcommand\\textbox[2]{\\parbox{#1\\textwidth}{#2}}\n"
    tex += "\\newcolumntype{C}{>{\\centering\\arraybackslash}X}\n"
    tex += "\\pagenumbering{gobble}\n"
    tex += "\\begin{document}\n"
    #tex += "\\textbox{.25}{\\hfill}\\textbox{.5}{\\Huge \\centering " + title + " \\Large (" + key + ")\\hfill} \\large \\textbox{.25}{\\hfill " + artist + "} \\large \n\n"
    tex += "\\begin{tabularx}{\\textwidth}{C r}\\Huge " + title + " \\Large (" + key + ") & \\large " + artist + "\\end{tabularx}\n\n"
    tex += "\\vspace{1em}\n"
    #print(tex)
    tex += "\\renewcommand{\\arraystretch}{1.5}\n"
    tex += "\\setlength{\\extrarowheight}{1.5em}\n"
    tex_sheet = "\\begin{tabularx}{\\textwidth}{l r| l@{\\hspace{1em}}X}\n"
    contains_sheet = False
    lyrics = ""
    for line in body.splitlines():
        if len(line) == 0:
            lyrics += '\n'
            continue
        if line[0] == '>':
            contains_sheet = True
            #tex += "\\\\[-1em] \\hline \\\\[-1em]\n"
            tex_sheet += "\\hline\n\\large "
            #tex += "\\\\[-.6em]\n"
            l = [*line[2:].replace('#',"\\#").replace('&','\\&').split(' ; '),'','']
            if "|" in l[2]:
                l[2] = l[2].replace('[','').replace(']','').replace('  ','\\enspace\\enspace')
                tex_sheet += "{} & {} & {} & {} \\\\".format(*l)
                continue
            elif len(l) > 3 and "|" in l[3]: # chord progression in middle column
                l[3] = l[3].replace('[','').replace(']','').replace('  ','\\enspace\\enspace')
                # tex += "{0:} & {1:} & {3:} & {2:} \\\\".format(*l)
                # continue
            tex_sheet += "{0:} & {1:} & {3:} & {2:} \\\\".format(*l)
        else:
            lyrics += line + '\n'

    tex_sheet += "\\hline\n"
    tex_sheet += "\\end{tabularx}\n\\pagebreak\n"
    tex_sheet += "\\renewcommand{\\arraystretch}{1}\n"
    if contains_sheet:
        tex += tex_sheet
    else:
        tex += "\\noindent\\rule{\\textwidth}{1pt}\n"
        tex += "\\vspace{-2em}\n"
    if not args.sheet:
        #tex += "\\pagebreak\n"
        if args.pdf_columns > 1:
            tex += "\\begin{multicols}{" + str(args.pdf_columns) + "}\n"
        tex += "\\normalsize"
        tex += out(lyrics)
        if args.pdf_columns > 1:
            tex += "\\end{multicols}\n"
    tex += "\\end{document}\n"
    basename = os.path.abspath(args.file).rsplit('.',1)[0]
    targetname = basename.rsplit('/',1)[1]

    if args.output_folder != "./":
        cwd = os.getcwd()
        if not os.path.exists(args.output_folder):
            q = input("The directory '{}' does not exist. Create? [Y/n] ".format(args.output_folder))
            if q not in ["n", 'N']:
                os.mkdir(args.output_folder,0o755)
            else:
                args.output_folder = cwd
        os.chdir(args.output_folder)
    # print(os.getcwd())
    # print(basename)
    targetname = os.path.join(os.getcwd(),targetname)
    # print(targetname)
    # input()
    with open("{}.tex".format(targetname),'w') as texfile:
        texfile.write(tex)
    #remove("{}.pdf".format(basename))
    if args.verbose:
        o = subprocess.call("xelatex {}.tex".format(targetname),shell=True)
    else:
        o = subprocess.call("xelatex {}.tex".format(targetname),shell=True,stdout=subprocess.DEVNULL)
    if o != 0:
        return
    # cleanup
    for i in ["tex","aux","log"]:
        os.remove("{}.{}".format(targetname,i))

    if args.output_folder != "./":
        os.chdir(cwd)

with open(os.path.expanduser(args.file), "r") as textfile:
    text = textfile.readlines()
    body = "".join(text[text.index("---\n")+1:])
    text = "".join(text[:text.index("---\n")])
    title = match_after("(?<=^# ).*", text)
    artist = match_after("(?<=^## ).*", text)
    key = match_after("(?<=^### ).*", text)
    key_shift_symbol = '+'

    if "+" in key:
        key_shift = int(match_after(r"(?<=\+).*", key))
        key = Chord(key.split("+")[0].strip())
    elif "-" in key:
        key_shift = -int(match_after(r"(?<=\-).*", key))
        key = Chord(key.split("-")[0].strip())
    else:
        key = Chord(key)
    if args.transpose is not None:
        try:
            key_shift = int(args.transpose)
        except ValueError:
            key_shift = key.distance(args.transpose)
    if not args.no_chords and key_shift != 0:
        key_str = str(key)
        if key_shift < 0:
            key_shift_symbol = '-'
        key = '{} {} {} = {}'.format(key_str,key_shift_symbol,abs(key_shift),key.transpose(key_shift))
    else:
        key_shift = 0
        key = str(key)
    print("{} - {} ({})".format(title, artist, key))
    

    # transpose
    def trans(matchobject):
        chord = matchobject[0].replace("[", "").replace("]", "")
        return "[" + str(Chord(chord).transpose(key_shift)) + "]"
    if args.transpose is not None or args.transposed:
        if key_shift != 0:
            body = re.sub(r"\[[a-zA-Z0-9#/]+\]", trans, body)
    elif args.no_chords:
        body = re.sub(r"\[[a-zA-Z0-9#/]+\]", "", body)

    if args.pdf:
        pdf(body,title,artist,key)
    elif '>' in body:
        print(sheet(body),end='')
    else:
        print(out(body))
