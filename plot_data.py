#!/usr/bin/python

from sys import argv
import itertools
import functools
import re

SEPARATOR = ','
NUMERICAL = '[0-9]+'
re_numerical = re.compile(NUMERICAL)

keydict = {}
labels = []

def explode(line):
    return line.split(SEPARATOR)

def value(string):
    if string == '-':
        return None
    if re_numerical.match(string):
        return int(string)
    return string

def read_datafile(f):
    benchmarks = []
    labels = explode(f.readline())[:-1]
    for i, label in enumerate(labels):
        keydict[label] = i
    for line in f:
        benchmarks.append(
            explode(line)[:-1])

    return benchmarks

def extract_data(benchmarks, group, variable, measure):
    group_elements = explode(group)
    groups = itertools.product(group_elements, repeat=2)

    key_complement = set(labels)
    key_complement.remove(variable)

    sorted_keys = list(key_complement)
    sorted_keys.append(variable)
    compare_function = functools.partial(comp_function, sorted_keys)

    sorted_benchmarks = sorted(benchmarks, cmp=compare_function)
    return sorted_benchmarks

def comp_function(keys, left, right):
    for key in keys:
        l = left[key]
        r = right[key]

        if l == None:
            return -1
        if r == None:
            return 1
        if type(l) == int:
            if l < r:
                return -1
            if l > r:
                return 1
            if l == r:
                return 0

def print_benchmark(bm):
    for key in bm.keys():
        print str(bm[key]),
    print
    

if __name__ == '__main__':
    if len(argv) != 5:
        print "\nUsage: python plot_data.py filename group variable measure"
        exit(1)

    filename = argv[1]
    group = argv[2]
    variable = argv[3]
    measure = argv[4]

    f = open(filename)
    try:
        benchmarks = read_datafile(f)
    finally:
        f.close()

    data = extract_data(benchmarks, group, variable, measure)

    print(' '.join(data[0].keys()))
    for bm in data:
        print_benchmark(bm)

    print(len(data[0].keys()))
        
    exit(0)


    
