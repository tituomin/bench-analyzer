#!/usr/bin/python

import re
from collections import OrderedDict as odict

SEPARATOR = ','
RE_EMPTY = re.compile('^\s*$')
RE_NUMERICAL = re.compile('-?[0-9]+')


def explode(line):
    return line.split(SEPARATOR)

def value(string, key=None):
    if key == 'class':
        return string.split('.')[-1]
    if string == '-' or RE_EMPTY.match(string):
        return None
    if RE_NUMERICAL.match(string):
        return int(string)
    else:
        return string

def empty_label():
    empty_label.cnt += 1
    return 'empty_{0}'.format(empty_label.cnt)

empty_label.cnt = 0

def read_datafiles(files):
    print 'Reading from %s files' % len(files)
    benchmarks = []
    #-1: there is an empty field at the end...

    keys_with_values = set()
    all_keys = set()

    for i, f in enumerate(files):
        line = f.readline()
        labels = explode(line)
        for i, l in enumerate(labels):
            # account for the fact that there might be an empty label
            # and corresponding column (usually the last)
            if RE_EMPTY.match(l):
                labels[i] = empty_label()

        all_keys.update(labels)

        line = f.readline()
        lineno = 1
        while line != '':
            exploded_line = explode(line)
            if len(labels) != len(exploded_line):
                print 'missing values', f.name, 'line', lineno, 'labels', len(labels), 'values', len(exploded_line)
                exit(1)

            benchmark = dict()

            for key, string in zip(labels, exploded_line):
                benchmark[key] = value(string, key=key)

                if value(string, key=key) != None:
                    keys_with_values.add(key)

            benchmarks.append(benchmark)
            line = f.readline()
            lineno += 1

    keys_without_values = all_keys - keys_with_values
    print 'No values for', keys_without_values

    benchmark_keycount = None
    for benchmark in benchmarks:
        for key in keys_without_values:
            if key in benchmark:
                del benchmark[key]
        current_keycount = len(benchmark.keys())
        benchmark_keycount = benchmark_keycount or current_keycount
        if benchmark_keycount != current_keycount:
            print "Benchmarks have different amount of data", benchmark_keycount, current_keycount
            exit(1)

    print 'Read %d lines' % (lineno - 1)
    return benchmarks

def read_measurement_metadata(mfile):
    compatibles = odict()
    measurement = None
    line = None

    while line != '':
        skipped = False
        while line == "\n":
            line = mfile.readline()
            skipped = True

        if skipped:
            if measurement:
                if 'tools' in measurement:
                    measurement['tool'] = measurement['tools']
                revision = measurement.get('code-revision')
                checksum = measurement.get('code-checksum')
                repetitions = measurement.get('repetitions')
                tool = measurement.get('tool')
                cpufreq = measurement.get('cpu-freq')
                benchmark_set = measurement.get('benchmark-set')
                substring_filter = measurement.get('substring-filter')
                if measurement.get('rounds') == None:
                    measurement['rounds'] = 1
                
                if revision and repetitions:
                        key = (revision, checksum, repetitions, tool, cpufreq, benchmark_set, substring_filter)
                        if key not in compatibles:
                            compatibles[key] = []
                        compatibles[key].append(measurement)
            measurement = {}

        if line != None:
            splitted = line.split()
            if len(splitted) > 1:
                key = splitted[0].rstrip(':')
                val = ' '.join(splitted[1:])
                measurement[key] = val.strip()

        line = mfile.readline()        

    return compatibles
