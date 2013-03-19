#!/usr/bin/python

from sys import argv
import itertools
import functools
import re
import pprint

pp = pprint.PrettyPrinter(depth=10, indent=4)


SEPARATOR = ','
NUMERICAL = '[0-9]+'
re_numerical = re.compile(NUMERICAL)

def explode(line):
    return line.split(SEPARATOR)

def value(string):
    if string == '-':
        return None
    if re_numerical.match(string):
        return int(string)
    return string

def read_datafile(f, variable):
    benchmarks = []
    labels = explode(f.readline())[:-1]
    for line in f:
        benchmarks.append(
            dict([(key,value(string)) for key, string in
                   zip(labels, explode(line)[:-1])]))
            
    return benchmarks

def extract_data(benchmarks, group, variable, measure):
    series_collection = []

    focus = explode(group)
    focus.append(variable)
    focus.append(measure)

    additional_info = []
    if re.match('parameter_type_.+count', variable):
        additional_info.append('parameter_count')
    additional_info.append('no')

    exclude_from_sorting = []
    exclude_from_sorting.extend(additional_info)
    exclude_from_sorting.extend(focus)

    labels = benchmarks[0].keys()
    sorted_keys = filter(lambda x: not x in exclude_from_sorting, labels)
    sorted_keys.extend(exclude_from_sorting)

    compare_function = functools.partial(comp_function, sorted_keys)
    sorted_benchmarks = sorted(benchmarks, cmp=compare_function)

    last_fixed = None
    series = None
    controlled_variables = filter(lambda x: not x in exclude_from_sorting, labels)

    for benchmark in sorted_benchmarks:
        fixed_data = tuple()
        for key in controlled_variables:
            fixed_data += (key, benchmark[key]),

        extra_data = tuple()
        for key in additional_info:
            extra_data += (key, benchmark[key]),

        element = {
            'fixed'  : fixed_data,
            'info'   : extra_data,
            variable : benchmark[variable],
            measure  : benchmark[measure],
            group    : benchmark[group]}

        if last_fixed == fixed_data:
            if (benchmark[group] not in series):
                series[benchmark[group]] = []
            series[benchmark[group]].append(element)

        else:
            if (series != None):
                append = True
                for bms in series.values():
                    if len(bms) < 2:
                        append = False
                if append:
                    series_collection.append(series)
            series = {benchmark[group]: [element]}

        last_fixed = fixed_data
        
    return series_collection

def comp_function(keys, left, right):
    for key in keys:
        l, r = left[key], right[key]
        if l == None:
            return 1
        if r == None:
            return -1
        if l < r:
            return 1
        if l > r:
            return -1
    return 0        
            

def print_benchmarks(data, group, variable, measure):
    for series in data:
        headers = []
        headers.append(variable)
        headers.extend(series.keys())
        print '# ' + measure + " / " + variable
        for header in headers:
            print '"{label}"'.format(label=header),
        print
        var_value = None
        group_vals = []
        for idx in range(0, len(series.values()[0])):
            i = 0
            for grp in series.values():
                if i == 0:
                    var_value = grp[idx][variable]
                    print var_value, 
                elif var_value != grp[idx][variable]:
                    print 'Error: groups have different variables'
                    exit(1)
                i += 1
                print grp[idx][measure],
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
        benchmarks = read_datafile(f, variable)
    finally:
        f.close()

    data = extract_data(benchmarks, group, variable, measure)
    
#    pp.pprint(data)

    print_benchmarks(data, group, variable, measure)

    exit(0)


    
