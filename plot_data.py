#!/usr/bin/python

from sys import argv
import itertools
import functools
import re
import pprint
import os
from copy import deepcopy

pp = pprint.PrettyPrinter(depth=10, indent=4)
debugdata = open('/tmp/debug.txt', 'w')



#parameter_type_boolean[]_count
#parameter_type_boolean_count
#parameter_type_byte[]_count
#parameter_type_byte_count
#parameter_type_char[]_count
#parameter_type_char_count
#parameter_type_double[]_count
#parameter_type_double_count
#parameter_type_float[]_count
#parameter_type_float_count
#parameter_type_int[]_count
#parameter_type_int_count
#parameter_type_java.lang.Class_count
#parameter_type_java.lang.Object[]_count
#parameter_type_java.lang.Object_count
#parameter_type_java.lang.String_count
#parameter_type_java.lang.Throwable_count
#parameter_type_long[]_count
#parameter_type_long_count
#parameter_type_short[]_count
#parameter_type_short_count

#return_type

#response_time_millis


types = [
        'boolean[]',
        'boolean',
        'byte[]',
        'byte',
        'char[]',
        'char',
        'double[]',
        'double',
        'float[]',
        'float',
        'int[]',
        'int',
        'long[]',
        'long',
        'short[]',
        'short',
        'java.lang.Class',
        'java.lang.Object[]',
        'java.lang.Object',
        'java.lang.String',
        'java.lang.Throwable']

SEPARATOR = ','
NUMERICAL = '[0-9]+'
re_numerical = re.compile(NUMERICAL)

def explode(line):
    return line.split(SEPARATOR)

def value(string):
    if string == '-':
        return 0
    if re_numerical.match(string):
        return int(string)
    return '"{s}"'.format(s=string)

def add_derived_values(benchmark):
    if (benchmark['parameter_count'] == 0):
        single_type = 'any'
    elif (benchmark['parameter_type_count'] == 1):
        for tp in types:
            if benchmark['parameter_type_{t}_count'.format(t=tp)] != 0:
                single_type = tp
                break
    else:
        single_type = None
    benchmark['single_type'] = single_type

def read_datafile(f):
    benchmarks = []
    #-1: there is an empty field at the end...
    labels = explode(f.readline())[:-1]
    for line in f:
        benchmark = dict([(key,value(string)) for key, string in
                          zip(labels, explode(line)[:-1])])
        add_derived_values(benchmark)
        benchmarks.append(benchmark)
            
    return benchmarks

def extract_data(benchmarks, group=None, variable=None, measure=None, min_series_length=2, min_series_width=2):
    series_collection = []
    exclude_from_sorting = []

    focus = explode(group)
    focus.append(variable)
    focus.append(measure)

    exclude_from_sorting.extend(focus)

    additional_info = []
    if re.match('parameter_type_.+count', variable):
        additional_info.append('parameter_count')
    additional_info.append('no')
    additional_info.append('description')

    exclude_from_sorting.extend(additional_info)

    labels = benchmarks[0].keys()
    sorted_keys = filter(lambda x: not x in exclude_from_sorting, labels)
    sorted_keys.extend(exclude_from_sorting)

    compare_function = functools.partial(comp_function, sorted_keys)
    sorted_benchmarks = sorted(benchmarks, cmp=compare_function)
    #pp.pprint(sorted_benchmarks)

    last_fixed = None
    series = None
    controlled_variables = filter(lambda x: not x in exclude_from_sorting, labels)

    for benchmark in sorted_benchmarks:
        fixed_data = tuple((key, benchmark[key]) for key in controlled_variables)
        extra_data = tuple((key, benchmark[key]) for key in additional_info)

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
                    if len(bms) < min_series_length:
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
            

def print_benchmarks(data, specs):
    group = specs.get('group')
    variable = specs.get('variable')
    measure = specs.get('measure')
    min_groups = specs.get('min_series_width', 1)

    result = ""
    for k, series in enumerate(data):
        if len(series.keys()) < min_groups:
            continue

        headers = []
        headers.append('"{v}"'.format(v=variable))
        headers.extend(series.keys())
        result += '"m:{measure} v:{variable} g:{group}" {headers}\n'.format(
            measure=measure,
            variable=variable,
            group=group, headers=" ".join(headers))

        var_value = None
        group_vals = []

        for idx in range(0, len(series.values()[0])):
            i = 0
            for key, grp in series.iteritems():
                if i == 0:
                    try:
                        var_value = grp[idx][variable]
                    except KeyError as e:
                        print variable
                    result += str(dict(grp[idx]['info'])['no']) + ' ' + str(var_value) + ' '
                elif var_value != grp[idx][variable]:
                    print 'Error: groups have different variables'
                    print 'expected', var_value, 'has', grp[idx][variable]
                    print 'key', key, 'k', k, 'series keys', series.keys()
                    exit(1)
                i += 1
                result += str(grp[idx][measure]) + ' '

            result += "\n"
        result += "\n\n"
    return result

init_plots_gp = """
set terminal pdfcairo size 32cm,18cm
set output '{filename}'
set key outside
set xlabel "Number of parameters"
set ylabel "Response time (ms)"
"""
#print "set size 0.6,0.6"
#set label 1 "foo weoigjew goijwegoe" at graph 1.1,0

plot_simple_groups = """
set title '{title}'
unset label 1
plot for [I=3:{last_column}] '{filename}' index {index} using 2:I title columnhead with linespoints
"""

def plot_benchmarks(benchmarks, output, plotpath):
    print init_plots_gp.format(filename=output)

    for i, ptype in enumerate(types):
        filename = os.path.join(plotpath, "plotdata_{num}.data".format(num=i))
        filtered_benchmarks = filter(lambda x: (x['single_type'] in [ptype, 'any']), deepcopy(benchmarks))
        for bm in filtered_benchmarks:
            del bm['single_type']
            del bm['parameter_type_count']
            for key in ["parameter_type_{t}_count".format(t=tp) for tp in types]:
                if key in bm:
                    del bm[key]
        
        # debugdata.write("\n")
        # debugdata.write(pp.pformat(filtered_benchmarks))
        # debugdata.write("\n")

        write_plotdata(plotpath, filename, filtered_benchmarks, {
             'group'    : 'direction',
             'variable' : 'parameter_count', 
             'measure'  : 'response_time_millis'
             })
        print(plot_simple_groups.format(
            title = ptype, filename = filename, index = 0, last_column = 6))

    filtered_benchmarks = deepcopy(benchmarks)
    for bm in filtered_benchmarks:
        for key in ["parameter_type_{t}_count".format(t=tp) for tp in types]:
            del bm[key]

    filename = os.path.join(plotpath, 'plotdata_typegroups.data')
    data = write_plotdata(plotpath, filename, filtered_benchmarks, {
        'group'    : 'single_type',
        'measure'  : 'response_time_millis',
        'variable' : 'parameter_count'})
    debugdata.write(pp.pformat(data))

    directions = []
    for plot in data:
        dirc = [val for key,val in (plot.values())[0][0]['fixed'] if key == 'direction']
        if dirc != None:
            directions.append(dirc[0])

    for index in range(0,4):
        print(plot_simple_groups.format(
                title = 'type grouping ' + directions[index], filename = filename, index = index, last_column = len(types)+2))

    filename = os.path.join(plotpath, 'plotdata_returntypes.data')
    write_plotdata(plotpath, filename, benchmarks, {
            'group'    : 'return_type',
            'measure'  : 'response_time_millis',
            'variable' : 'direction',
            'min_series_width' : 2
            })
    print ("set title 'return types'\n"
           "unset label 1\n"
           "plot for [I=3:{limit}] '{filename}' using I:xtic(2) title columnhead with linespoints").format(
        limit=len(types)+2, filename = filename)
        
def write_plotdata(path, filename, benchmarks, specs):
    plotdata = open(filename, 'w')
    data = extract_data(benchmarks, **specs)
    # debugdata.write(pp.pformat(specs) + "\n\n")
    # debugdata.write(pp.pformat(data))
    plotdata.write(print_benchmarks(data, specs))
    return data


if __name__ == '__main__':
    if len(argv) <  3 or len(argv) > 4:
        print "\nUsage: python plot_data.py benchmarkdata outputfilename plotdatapath"
        exit(1)

    filename = argv[1]
    output = argv[2]

    if len(argv) == 4:
        plotpath = argv[3]
    else:
        plotpath = '/tmp'

    f = open(filename)
    try:
        benchmarks = read_datafile(f)
    finally:
        f.close()

    plot_benchmarks(benchmarks, output, plotpath)
    exit(0)
    
