#!/usr/bin/env python3

from lxml import html
import argparse
import requests
from os.path import expanduser
from os import remove,get_terminal_size
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
        idx = Chord.FLAT.index(self.base) if self.base in Chord.FLAT else Chord.SHARP.index(self.base)
        if amount < 0:
            self.base = Chord.FLAT[(idx + amount) % 12]
        else:
            self.base = Chord.SHARP[(idx + amount) % 12]
        return self
    
    def __str__(self):
        s = self.base if self.third else self.base.lower()
        return s + self.addition


key_shift = 0

parser = argparse.ArgumentParser()
parser.add_argument("file")
key_group = parser.add_mutually_exclusive_group()
key_group.add_argument("-n", "--no-chords", action="store_true")
key_group.add_argument("-t", "--transposed", action="store_true")
key_group.add_argument("-T", "--transpose", type=int, help="shift in half tone steps") #TODO: accept another key instead of shift
parser.add_argument("-C", "--no-color", action="store_true", help="disable color output of chords")
parser.add_argument("-s", "--sheet", action="store_true", help="only print the sheet")
parser.add_argument("-p", "--pdf", action="store_true", help="instead of printing to stdout, create pdf file")
parser.add_argument("-l", "--lyrics", action="store_true", help="only print the lyrics")

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

    
    for line in text.splitlines():
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

        if line == '':
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

    # wrap text if in terminal mode and more than $lines have to be printed
    colwidth = int(get_terminal_size()[0]/2)
    if linecount + 3 > get_terminal_size()[1] and not args.pdf:
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
        return output_2
    return output


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

def pdf(body,title,artist,key):
    tex = "\\documentclass[notitlepage,14pt]{extarticle}\n"
    tex += "\\usepackage[a4paper,margin=0.8in]{geometry}\n"
    tex += "\\usepackage{fontspec}\n"
    tex += "\\usepackage{tabularx}\n"
    tex += "\\usepackage{array}\n"
    tex += "\\setmainfont[Ligatures=TeX]{MuseJazzText}\n"
    tex += "\\newcommand\\textbox[2]{\\parbox{#1\\textwidth}{#2}}\n"
    tex += "\\newcolumntype{C}{>{\\centering\\arraybackslash}X}\n"
    tex += "\\pagenumbering{gobble}\n"
    tex += "\\begin{document}\n"
    #tex += "\\textbox{.25}{\\hfill}\\textbox{.5}{\\Huge \\centering " + title + " \\Large (" + key + ")\\hfill} \\large \\textbox{.25}{\\hfill " + artist + "} \\large \n\n"
    tex += "\\begin{tabularx}{\\textwidth}{C r}\\Huge " + title + " \\Large (" + key + ") & \\large " + artist + "\\end{tabularx}\n\n"
    tex += "\\vspace{1em}\n"
    print(tex)
    tex += "\\renewcommand{\\arraystretch}{1.5}\n"
    tex += "\\setlength{\\extrarowheight}{1.5em}\n"
    tex += "\\begin{tabularx}{\\textwidth}{l r| l@{\\hspace{1em}}X}\n"
    lyrics = ""
    for line in body.splitlines():
        if len(line) == 0:
            lyrics += '\n'
            continue
        if line[0] == '>':
            #tex += "\\\\[-1em] \\hline \\\\[-1em]\n"
            tex += "\\hline\n\\large "
            #tex += "\\\\[-.6em]\n"
            l = [*line[2:].replace('#',"\\#").replace('&','\\&').split(' ; '),'','']
            if "|" in l[2]:
                l[2] = l[2].replace('[','').replace(']','').replace('  ','\\enspace\\enspace')
                tex += "{} & {} & {} & {} \\\\".format(*l)
                continue
            elif len(l) > 3 and "|" in l[3]: # chord progression in middle column
                l[3] = l[3].replace('[','').replace(']','').replace('  ','\\enspace\\enspace')
                # tex += "{0:} & {1:} & {3:} & {2:} \\\\".format(*l)
                # continue
            tex += "{0:} & {1:} & {3:} & {2:} \\\\".format(*l)
        else:
            lyrics += line + '\n'

    tex += "\\hline\n"
    tex += "\\end{tabularx}\n"
    tex += "\\renewcommand{\\arraystretch}{1}\n"
    if not args.sheet:
        #tex += "\\pagebreak\n"
        tex += "\\normalsize\\begin{verbatim}\n"
        tex += out(lyrics)
        tex += "\\end{verbatim}\n"
    tex += "\\end{document}\n"
    basename = args.file.rsplit('.',1)[0]
    with open("{}.tex".format(basename),'w') as texfile:
        texfile.write(tex)
    #remove("{}.pdf".format(basename))
    o = subprocess.call("xelatex {}.tex".format(basename),shell=True)
    if o != 0:
        return
    # cleanup
    for i in ["tex","aux","log"]:
        remove("{}.{}".format(basename,i))

with open(expanduser(args.file), "r") as textfile:
    text = textfile.readlines()
    body = "".join(text[text.index("---\n")+1:])
    text = "".join(text[:text.index("---\n")])
    title = match_after("(?<=^# ).*", text)
    artist = match_after("(?<=^## ).*", text)
    key = match_after("(?<=^### ).*", text)
    
    if "+" in key:
        key_shift = int(match_after(r"(?<=\+).*", key))
        key = Chord(key.split("+")[0].strip())
    elif "-" in key:
        key_shift = -int(match_after(r"(?<=\-).*", key))
        key = Chord(key.split("-")[0].strip())
    else:
        key = Chord(key)
    if args.transpose is not None:
        key_shift = args.transpose
    if not args.no_chords and key_shift != 0:
        key_str = str(key)
        key = '{} + {} = {}'.format(key_str,key_shift,key.transpose(key_shift))
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
            body = re.sub(r"\[[a-zA-Z0-9#]+\]", trans, body)
    elif args.no_chords:
        body = re.sub(r"\[[a-zA-Z0-9#]+\]", "", body)

    if args.pdf:
        pdf(body,title,artist,key)
    elif '>' in body:
        print(sheet(body),end='')
    else:
        print(out(body))
