#!/usr/bin/env python3

from lxml import html
import argparse
import requests
from os.path import expanduser
import re

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
        self.base = Chord.SHARP[(idx + amount) % 12]
        return self
    
    def __str__(self):
        s = self.base if self.third else self.base.lower()
        return s + self.addition


key_shift = 0

parser = argparse.ArgumentParser()
parser.add_argument("file")
key_group = parser.add_mutually_exclusive_group()
key_group.add_argument("-o", "--original", action="store_true")
key_group.add_argument("-t", "--transposed", action="store_true")
key_group.add_argument("-T", "--transpose", type=int, help="shift in half tone steps") #TODO: accept another key instead of shift
parser.add_argument("-C", "--no-color", action="store_true", help="disable color output of chords")

args = parser.parse_args()


def match_after(expr, target):
    return re.search(expr, target, re.MULTILINE)[0]

def out(text):
    def trans(matchobject):
        chord = matchobject[0].replace("[", "").replace("]", "")
        return "[" + str(Chord(chord).transpose(key_shift)) + "]"
    if args.transpose or args.transposed is not None:
        if key_shift != 0:
            text = re.sub(r"\[\w+\]", trans, text)
    elif not args.original:
        text = re.sub(r"\[\w+\]", "", text)
    ischord = False
    output = ""
    chordline = ""
    lyrline = ""
    chordlength = 0
    for line in text.splitlines():
        for c in line:
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
        if chordline.rstrip() != "":
            output += "\033[1;35m" + chordline + "\033[0;0m\n"
        if not (chordline.rstrip() != "" and lyrline.rstrip() == ""):
            output += lyrline + "\n"
        chordline = ""
        lyrline = ""
        chordlength = 0
    print(output)

with open(expanduser(args.file), "r") as textfile:
    text = textfile.readlines()
    body = "".join(text[text.index("---\n")+1:])
    text = "".join(text)
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
    if not args.original:
        key = str(key.transpose(key_shift))
    else:
        key_shift = 0
        key = str(key)
    print("{} - {} ({})".format(title, artist, key))
    out(body)
