#!/usr/bin/python

from sys import argv
import itertools
import functools
import re

SEPARATOR = ','
NUMERICAL = '[0-9]+'
re_numerical = re.compile(NUMERICAL)

dependencies = [
    # if key (left) chosen as variable,
    # corresponding keys (right) must be removed
    # since they are not independent from the key
    ('parameter_count'        , 'parameter_type_.+count'),
    ('parameter_type_count'   , 'parameter_count'),
    ('parameter_type_.+count' , 'parameter_count')]

def remove_dependencies(series, sorted_keys, variable):
    for benchmark in benchmarks:
        for var, removable in dependencies:
            if re.match(var, variable):
                for key in benchmark.keys():
                    if re.match(removable, key):
                        del benchmark[key]
                for key in sorted_keys:
                    if re.match(removable, key):
                        sorted_keys.remove(key)

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
    for line in f:
        benchmarks.append(
            dict([(key,value(string)) for key, string in
                   zip(labels, explode(line)[:-1])]))
            
    return benchmarks

def extract_data(benchmarks, group, variable, measure):
    series_collection = []

    exclude_list = explode(group)
    exclude_list.append(variable)
    exclude_list.append(measure)

    labels = benchmarks[0].keys()
    sorted_keys = filter(lambda x: not x in exclude_list, labels)
    sorted_keys.extend(exclude_list)

    controlled_variables = filter(lambda x: not x in exclude_list, labels)

    compare_function = functools.partial(comp_function, sorted_keys)
    sorted_benchmarks = sorted(benchmarks, cmp=compare_function)

    last_fixed = None
    series = []
    for benchmark in sorted_benchmarks:
        fixed_data = tuple()
        for key in controlled_variables:
            fixed_data += benchmark[key],

        element = {
            'fixed' : fixed_data,
            variable : benchmark[variable],
            measure : benchmark[measure],
            group : benchmark[group]}

        if last_fixed == fixed_data:
            series.append(element)

        else:
            series_collection.append(series)
            series = [element]

        last_fixed = fixed_data
        
    return series_collection, sorted_keys

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

def print_benchmarks(data, sorted_keys):
    i = 0
    for series in data:
        for benchmark in series:
            if i == 0:
                print ' '.join(benchmark.keys())
            print ' '.join(benchmark.values())
        print ' ---------- '

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

    data, keys = extract_data(benchmarks, group, variable, measure)
    remove_dependencies(data, keys, variable)

    print_benchmarks(data, keys)

    exit(0)


    
