#!/usr/bin/python

from sys import argv
import itertools
import functools
import re
import pprint
import os
from copy import deepcopy
from collections import OrderedDict as odict
from subprocess import call
import shutil

pp = pprint.PrettyPrinter(depth=10, indent=4)
debugdata = open('/tmp/debug.txt', 'w')

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
    else:
        return '"{s}"'.format(s=string)

def add_derived_values(benchmark, index):
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
    benchmark['index'] = index

def read_datafiles(files):
    benchmarks = []
    #-1: there is an empty field at the end...

    line = None
    for f in files:
        line = f.readline()
    labels = explode(line)[:-1]

    for i, f in enumerate(files):
        line = f.readline()
        lineno = 1
        while line != '':
            exploded_line = explode(line)[:-1]
            if len(labels) != len(exploded_line):
                print 'missing values', f.name, 'line', lineno, 'labels', len(labels), 'values', len(exploded_line)
                exit(1)
            benchmark = dict(
                [(key,value(string)) for
                 key, string in
                 zip(labels, exploded_line)])

            add_derived_values(benchmark, i)
            benchmarks.append(benchmark)
            line = f.readline()
            lineno += 1
    return benchmarks

def extract_data(benchmarks,
                 group=None, variable=None, measure=None,
                 min_series_length=2, min_series_width=2, sort=None, measure_count=None, real_measure_count=None):

    if variable != 'index':
        for bm in benchmarks:
            del bm['index']
        
    series_collection = []
    exclude_from_sorting = []

    # additional data fields that should be excluded
    # from all sorting / variable controlling
    additional_info = []
    if re.match('parameter_type_.+count', variable):
        additional_info.append('parameter_count')
    additional_info.append('no')
    additional_info.append('description')

    exclude_from_sorting.extend(additional_info)

    # the actual fields we're analyzing
    focus = explode(group)
    focus.append(variable)
    focus.append(measure)

    exclude_from_sorting.extend(focus)

    labels = benchmarks[0].keys()
    sorted_keys = filter(lambda x: not x in exclude_from_sorting, labels)
    sorted_keys.extend(exclude_from_sorting)

    compare_function = functools.partial(comp_function, sorted_keys)
    sorted_benchmarks = sorted(benchmarks, cmp=compare_function)

    last_fixed = None
    series = None
    controlled_variables = filter(lambda x: not x in exclude_from_sorting, labels)

    benchmark = None
    values = []
    skip = False

    if len(benchmarks) % measure_count != 0:
        print 'error not divisible by', measure_count, len(benchmarks)
        exit(1)

    for i in range(0, len(benchmarks), measure_count):
        benchmarks_to_combine = sorted_benchmarks[i:i+measure_count]
        values = []
        last_bm = None
        for bm in benchmarks_to_combine:
            values.append(bm[measure])

            if last_bm != None:
                for key in filter(lambda x: x != measure, bm.keys()):
                    if last_bm[key] != bm[key]:
                        print 'error non matching keys', key
            last_bm = bm

        # take measure_count measurements, combine
        benchmark = benchmarks_to_combine[0]
        benchmark[measure] = mean(values) # todo: parametrize combining function

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


def mean(values):
    return min(values)
    #return sorted(values)[1:-1][(len(values)-2)/2]

def comp_function(keys, left, right):
    for key in keys:
        if key == 'index':
            return 0
        l, r = left[key], right[key]
        ordering = {
            '"C > C"' : 0,
            '"J > C"' : 1,
            '"J > J"' : 2,
            '"C > J"' : 3
            }

        if l in ordering.keys() and r in ordering.keys():
            l, r = ordering[l], ordering[r]

        if l == None:
            return -1
        if r == None:
            return 1
        if l < r:
            return -1
        if l > r:
            return 1
    return 0        
            

def print_benchmarks(data, group=None, variable=None, measure=None, sort=None, min_series_width=None, measure_count=None):
    result = ""
    for k, series in enumerate(data):
        if len(series.keys()) < min_series_width:
            # there are not enough groups to display
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
                    debugdata.write(pp.pformat(series))
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

def plot_benchmarks(benchmarks, output, plotpath, gnuplotcommands, measure_count=None):
    f = open(gnuplotcommands, 'w')

    f.write(init_plots_gp.format(filename=output))

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
             'measure'  : 'response_time_millis',
             'measure_count' : measure_count
             
             })
        f.write(plot_simple_groups.format(
            title = ptype, filename = filename, index = 0, last_column = 6))

    filtered_benchmarks = deepcopy(benchmarks)
    for bm in filtered_benchmarks:
        for key in ["parameter_type_{t}_count".format(t=tp) for tp in types]:
            del bm[key]

    filename = os.path.join(plotpath, 'plotdata_typegroups.data')
    data = write_plotdata(plotpath, filename, filtered_benchmarks, {
        'group'    : 'single_type',
        'measure'  : 'response_time_millis',
        'variable' : 'parameter_count',
        'measure_count' : measure_count})
#    debugdata.write(pp.pformat(data))

    directions = []
    for plot in data:
        dirc = [val for key,val in (plot.values())[0][0]['fixed'] if key == 'direction']
        if dirc != None:
            directions.append(dirc[0])

    for index in range(0,4):
        f.write(plot_simple_groups.format(
                title = 'type grouping ' + directions[index], filename = filename, index = index, last_column = len(types)+2))

    filtered_benchmarks = filter(lambda x: x['return_type'] != '"void"', deepcopy(benchmarks))
    filename = os.path.join(plotpath, 'plotdata_returntypes.data')
    write_plotdata(plotpath, filename, filtered_benchmarks, {
            'group'    : 'return_type',
            'measure'  : 'response_time_millis',
            'variable' : 'direction',
            'min_series_width' : 2,
            'sort'     : 'response_time_millis',
             'measure_count' : measure_count
            })

    f.write("set title 'return types'\n"
           "unset label 1\n"
           "plot for [I=3:{limit}] '{filename}' using I:xtic(2) title columnhead with linespoints".format(
        limit=len(types)+2, filename = filename))
        
def write_plotdata(path, filename, benchmarks, specs):
    plotdata = open(filename, 'w')
    data = extract_data(benchmarks, **specs)
    plotdata.write(print_benchmarks(data, **specs))
    return data


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
                checksum = measurement.get('code-checksum')
                repetitions = measurement.get('repetitions')
                tool = measurement.get('tool')
                if checksum and repetitions:
                        key = (checksum, repetitions, tool)
                        if key not in compatibles:
                            compatibles[key] = []
                        compatibles[key].append(measurement)
            measurement = {}

        if line != None:
            splitted = line.split(': ')
            if len(splitted) > 1:
                key = splitted[0]
                val = splitted[1]
                measurement[key] = val.strip()

        line = mfile.readline()        

    return compatibles

MEASUREMENT_FILE = 'measurements.txt'
MEASUREMENT_PATH = '/home/tituomin/Ubuntu One/gradu/measurements'
DEVICE_PATH = '/sdcard/results'
PLOTPATH = '/tmp'
TOOL_NAMESPACE = 'fi.helsinki.cs.tituomin.nativebenchmark.measuringtool'

def sync_measurements(dev_path, host_path, filename):
    old_path = host_path + '/' + filename
    tmp_path = '/tmp/' + filename
    success = call(['adb', 'pull',
                    dev_path  + '/' + filename,
                    tmp_path])
    if success == 0:
        if os.path.exists(old_path):
            size_new = os.path.getsize(tmp_path)
            size_old = os.path.getsize(old_path)
            if size_new < size_old:
                print "Warning: new file contains less data than the old. Aborting."
                exit(2)
        shutil.move(tmp_path, old_path)

    else:
        print "Could not get new measurements, continuing with old."


if __name__ == '__main__':
    if len(argv) <  4 or len(argv) > 4:
        print "\n    Usage: python plot_data.py pdfoutput gnuplotcommands limit\n"
        exit(1)

    output = argv[1]
    gnuplotoutput = argv[2]
    limit = argv[3]

    sync_measurements(DEVICE_PATH, MEASUREMENT_PATH, MEASUREMENT_FILE)

    f = open(os.path.join(MEASUREMENT_PATH, MEASUREMENT_FILE))

    try:
        measurements = read_measurement_metadata(f)
    finally:
        f.close()

    print "\nAvailable compatible measurements. Choose one"
    i = 1
    limited_measurements = filter(lambda x: int(x[0].get('repetitions', 0)) >= int(limit),
                                  measurements.values())

    for m in limited_measurements:
            print """
    [{idx}]:     total measurements: {num}
                    repetitions: {reps}
                       checksum: {ck}
                           tool: {tool}
                          dates: {first} -
                                 {last}
    """.format(num=len(m), idx=i, reps=m[0].get('repetitions'),
               ck=m[0].get('code-checksum'),
               tool=m[0].get('tool'),
               first=m[0]['start'], last=m[-1]['end'])

            i += 1
    
    response = raw_input("Choose set 1-{last} >> ".format(last=i-1))
    benchmark_group = limited_measurements[int(response) - 1]

    filenames = []
    files = []
    for measurement in benchmark_group:
        if measurement['tool'] == TOOL_NAMESPACE + '.LinuxPerfRecordTool':
            basename = "perfdata-{n}.zip"
            print 'tool is perf'
        else:
            basename = "benchmarks-{n}.csv"
            print 'tool is recorder'
        filenames.append(
            basename.format(n=measurement['id']))

    for filename in filenames:
        sync_measurements(DEVICE_PATH, MEASUREMENT_PATH, filename)
    try:
        benchmarks = read_datafiles(files)
    finally:
        for f in files:
            f.close()

#    pp.pprint(benchmarks)

    measure_count = len(benchmark_group)
    plot_benchmarks(benchmarks, output, plotpath, gnuplotoutput, measure_count=measure_count)
    exit(0)
    
