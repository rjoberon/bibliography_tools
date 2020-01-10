#!/usr/bin/python3
# -*- coding: utf-8 -*-

#
# Given a BibTeX file and a list of keys, extracts data in TSV.
#
# Usage: see --help option
#
# Author: rja
#
# Bugs:
# - heuristics to identify correct entry from Crossref need improvement
#
# Changes:
# 2020-01-10 (rja)
# - added argparse
# - many cleanups and refactoring
# 2020-01-06 (rja)
# - initial version

import re
import sys
import csv
import argparse
import bibtexparser
from bibtexparser.bparser import BibTexParser
from habanero import Crossref


# reads all BibTeX entries from fname
def get_bibtex(f):
    parser = BibTexParser(common_strings=False)
    parser.ignore_nonstandard_types = False
    parser.homogenise_fields = True
    parser.customization = clean_tex

    return bibtexparser.load(f, parser)


# reads all lines of f into a list
def get_keys(f):
    if f:
        return [line.strip() for line in f]
    return None


# to remove newlines from BibTeX fields in clean_fields()
re_newline = re.compile(r"\s*\n\s*")


# removes line breaks from some fields
def clean_fields(record):
    for field in ["title", "author", "editor", "journal", "booktitle", "series"]:
        if field in record:
            record[field] = re_newline.sub(" ", record[field])
    return record


# some cleansing, including conversion of LaTeX encoding
def clean_tex(record):
    return clean_fields(bibtexparser.customization.convert_to_unicode(record))


# checks which keys are not contained in the BibTeX database
def check_keys(bib, keys):
    missing = []
    for key in keys:
        if key not in bib.entries_dict:
            missing.append(key)
    return missing


# removes all entries from bib whose key (id) is not in keys
def filter_keys(bib, keys):
    # rebuild entries
    bib.entries = [entry for entry in bib.entries if entry["ID"] in keys]
    # remove from corresponding dict
    for key in list(bib.entries_dict.keys()):
        if key in keys:
            del bib.entries_dict[key]


# writes BibTeX entries (some fields only) with the given keys as TSV into f
def write_tsv(bib, f, fields):
    writer = csv.DictWriter(f, fields.split(','), extrasaction='ignore', delimiter='\t')
    writer.writeheader()
    for entry in bib.entries:
        writer.writerow(entry)


# writes all BibTeX entries as BibTeX into f
def write_bib(bib, f):
    bibtexparser.dump(bib, f)


# Query crossref for each title and if a matching item could be found
# (cf. get_matching_item()), add the DOI.
def enrich_from_crossref(bib, email):
    cr = Crossref()
    if email:
        Crossref(mailto = email)
    okcount = 0
    print("entries where no exact matching entry could be found on Crossref:")
    for entry in bib.entries:
        res = cr.works(query_bibliographic = entry["title"])
        item = get_matching_item(entry, res['message']['items'])
        if item:
            okcount += 1
            enrich_entry(entry, item)
    print(okcount, "of", len(bib.entries), "had matching titles")


# Since Crossref returns several results, we here apply some
# heuristics to find the best matching item.
def get_matching_item(bibentry, items):
    # heuristic: rely on Crossref's ranking and take the first item
    item = items[0]
    # heuristic: do (almost) exact string matching on the title (only)
    if item.get("title")[0].casefold() == bibentry["title"].casefold():
        return item
    # debug output
    print(bibentry["ID"], bibentry["title"])
    print("  best Crossref match:", item.get("title"), item.get("DOI"))
    return None


# Add information from Crossref to BibTeX entry
def enrich_entry(bibentry, item):
    # currently, we only add the DOI
    doi = item.get("DOI")
    if "doi" in bibentry:
        # entry already has a DOI ... add some debug output on mismatch
        if bibentry["doi"].lower() != doi.lower():
            print(i, "DOI mismatch:", bibentry["doi"], "!=", doi)
    else:
        # enrich with DOI
        bibentry["doi"] = doi


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Enrich BibTeX entries with data from Crossref.')
    parser.add_argument('file', type=argparse.FileType('r', encoding='utf-8'), nargs='?', default=sys.stdin, help='BibTeX input file (default: STDIN)')
    parser.add_argument('-e', '--email', type=str, metavar="ADD", help="e-mail address (to enable faster Crossref polite API)")
    parser.add_argument('-f', '--format', type=str, metavar="FMT", help="output format (default: '%(default)s')", default="bib", choices=["bib", "tsv"])
    parser.add_argument('-k', '--keys', type=argparse.FileType('r', encoding='utf-8'), metavar="FILE", help='only handle entries with those keys (one per line)')
    parser.add_argument('-o', '--output', type=argparse.FileType('w', encoding='utf-8'), metavar="FILE", help='output file', required=True)
    parser.add_argument('-t', '--tsv-fields', type=str, metavar="F", help="fields to include in TSV output (separated by comma)")

    ["ENTRYTYPE", "ID", "doi", "year", "author", "title"]
    args = parser.parse_args()

    if args.format == "tsv" and (args.tsv_fields is None):
        parser.error("Format 'tsv' requires --tsv-fields.")

    # read BibTeX
    bibtex = get_bibtex(args.file)
    print("read", len(bibtex.entries), "entries")

    # read keys
    keys = get_keys(args.keys)
    print("read", len(keys), "keys")

    # check keys
    missing = check_keys(bibtex, keys)
    print(len(missing), "keys are missing:", missing)

    # filter keys
    filter_keys(bibtex, keys)
    print(len(bibtex.entries), "entries remaining after filtering")

    # enrich with data from Crossref
    enrich_from_crossref(bibtex, args.email)

    # write to file
    if args.format == "tsv":
        write_tsv(bibtex, args.output, args.tsv_fields)
    else:
        write_bib(bibtex, args.output)
