#!/usr/bin/python

from sys import argv
import itertools
import functools
import re
import pprint

pp = pprint.PrettyPrinter(depth=10, indent=4)

#direction
#native_private
#native_static
#no

#parameter_count

#parameter_type_count


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
        return None
    if re_numerical.match(string):
        return int(string)
    return '"{s}"'.format(s=string)

def add_derived_values(benchmark):
    if (benchmark['parameter_type_count'] == 1):
        for tp in types:
            if benchmark['parameter_type_{t}_count'.format(t=tp)] != None:
                single_type = tp
                break
    else:
        single_type = None
    benchmark['single_type'] = single_type

def read_datafile(f):
    benchmarks = []
    labels = explode(f.readline())[:-1]
    for line in f:
        benchmark = dict([(key,value(string)) for key, string in
                          zip(labels, explode(line)[:-1])])
        add_derived_values(benchmark)
        benchmarks.append(benchmark)
            
    return benchmarks

def extract_data(benchmarks, group=None, variable=None, measure=None, min_series_length=2, min_series_width=2):
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
            

def print_benchmarks(data, group=None, variable=None, measure=None, min_groups=1):
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
        
if __name__ == '__main__':
    if len(argv) != 2:
        print "\nUsage: python plot_data.py filename"
        exit(1)

    filename = argv[1]

    f = open(filename)
    try:
        benchmarks = read_datafile(f)
    finally:
        f.close()

    print "set terminal pdfcairo size 32cm,18cm"
    print "set output 'plot.pdf'"
    print "set key outside"
    print "set xlabel \"Number of parameters\""
    print "set ylabel \"Response time (ms)\""
    #print "set size 0.6,0.6"

    group = 'direction'
    for i, ptype in enumerate(types):

        specs = {
             'group'    : group,
             'variable' : 'parameter_type_{t}_count'.format(t=ptype), 
             'measure'  : 'response_time_millis'
             }
      
        data = extract_data(benchmarks, **specs)
        filename = "/tmp/plotdata_{num}.data".format(num=i)
        plotdata = open(filename, "w")
        plotdata.write(print_benchmarks(data, **specs))
#set label 1 "foo weoigjew goijwegoe" at graph 1.1,0

        print ("set title '{title}'\n"
               "unset label 1\n"
               "plot for [I=3:6] '{filename}' using 2:I title columnhead with linespoints").format(
            title=ptype, index=i, filename = filename )

    filtered_benchmarks = benchmarks[:]
    for bm in filtered_benchmarks:
        for key in ["parameter_type_{t}_count".format(t=tp) for tp in types]:
            del bm[key]

    specs = { 'group'   : 'single_type',
             'measure'  : 'response_time_millis',
             'variable' : 'parameter_count'}

    data = extract_data(filtered_benchmarks, **specs)
    #pp.pprint(data)

    filename = "/tmp/plotdata_typegroups.data"
    plotdata = open(filename, 'w')
    plotdata.write(print_benchmarks(data, **specs))

    for index in range(0,4):
        print ("set title 'type grouping'\n"
               "plot for [I=3:{limit}] '/tmp/plotdata_typegroups.data' index {index} using 2:I title columnhead with linespoints").format(
            limit=3+len(types) -1, index=index)


    specs = {
        'group'    : 'return_type',
        'measure'  : 'response_time_millis',
        'variable' : 'direction'
        }
    data = extract_data(benchmarks, min_series_length=2, **specs)

    #pp.pprint(data)

    filename ="/tmp/plotdata_returntypes.data"
    plotdata = open(filename, 'w')
    plotdata.write(print_benchmarks(data, min_groups=2, **specs))

    print ("set title 'return types'\n"
           "unset label 1\n"
           "plot for [I=3:{limit}] '{filename}' using I:xtic(2) title columnhead with linespoints").format(
        limit=3+len(types)-1, filename = filename)

    exit(0)


    
