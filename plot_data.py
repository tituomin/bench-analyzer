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
import uuid

pp = pprint.PrettyPrinter(depth=10, indent=4)
debugdata = open('/tmp/debug.txt', 'w')

reference_types = [
        'boolean[]',
        'byte[]',
        'char[]',
        'double[]',
        'float[]',
        'int[]',
        'long[]',
        'short[]',
        'java.lang.Object[]',
        'java.lang.Class',
        'java.lang.Object',
        'java.lang.String',
        'java.lang.Throwable'
    ]

primitive_types = [
        'boolean',
        'byte',
        'char',
        'double',
        'float',
        'int',
        'long',
        'short'
]

directions = []
for from_lang, to_lang in [('J', 'C'), ('J', 'J'), ('C','C'), ('C', 'J')]:
    directions.append("%s > %s" % (from_lang, to_lang))


types = reference_types[:]
types.extend(primitive_types)

SEPARATOR = ','
NUMERICAL = '-?[0-9]+'
re_numerical = re.compile(NUMERICAL)

def explode(line):
    return line.split(SEPARATOR)

def value(string):
    if string == '-':
        return 0
    if re_numerical.match(string):
        return int(string)
    else:
        return string

def add_derived_values(benchmark, index):
    single_type = None
    if (benchmark['parameter_count'] == 0):
        single_type = 'any'
    elif (benchmark['parameter_type_count'] == 1):
        for tp in types:
            if benchmark['parameter_type_{t}_count'.format(t=tp)] != 0:
                single_type = tp
                break
    benchmark['single_type'] = single_type
    benchmark['index'] = index

def read_datafiles(files):
    print 'Reading from %s files' % len(files)
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

            benchmark = odict(
                [(key,value(string)) for
                 key, string in
                 zip(labels, exploded_line)])

            add_derived_values(benchmark, i)
            benchmarks.append(benchmark)
            line = f.readline()
            lineno += 1
    print 'Read %d lines' % (lineno - 1)
    return benchmarks

def extract_data(benchmarks,
                 group=None, variable=None, measure=None,
                 min_series_length=2, sort=None, measure_count=None, min_series_width=None):

    if variable != 'index':
        for bm in benchmarks:
            del bm['index']
        
    # from all sorting / variable controlling
    additional_info = []
    if re.match('parameter_type_.+count', variable):
        additional_info.append('parameter_count')
    additional_info.extend(['no', 'description', 'class'])

    # the actual fields we're analyzing
    focus = explode(group)
    focus.append(variable)
    focus.append(measure)

    exclude_from_sorting = []
    exclude_from_sorting.extend(additional_info)
    exclude_from_sorting.extend(focus)

    controlled_variables = [x for x in benchmarks[0].keys() if x not in exclude_from_sorting]
    sorted_keys = controlled_variables[:]
    sorted_keys.extend(exclude_from_sorting)

    compare_function = functools.partial(comp_function, sorted_keys)
    sorted_benchmarks = sorted(benchmarks, cmp=compare_function)

    if len(benchmarks) % measure_count != 0:
        print 'error not divisible by', measure_count, len(benchmarks)
        exit(1)

    groups = odict()
    for i in range(0, len(benchmarks), measure_count):
        benchmarks_to_combine = sorted_benchmarks[i:i+measure_count]
        values = [bm[measure] for bm in benchmarks_to_combine]

        last_bm = None
        for bm in benchmarks_to_combine:
            if last_bm != None:
                for key in filter(lambda x: x != measure, bm.keys()):
                    if last_bm[key] != bm[key]:
                        print 'error non matching keys', key
            last_bm = bm

        # take measure_count measurements, combine
        benchmark = benchmarks_to_combine[0]
        benchmark[measure] = min(values) # todo: parametrize combining function

        fixed_data = tuple((key, benchmark[key]) for key in controlled_variables)
        extra_data = tuple((key, benchmark[key]) for key in additional_info)

        element = {
            'fixed'  : fixed_data,
            'info'   : extra_data,
            variable : benchmark[variable],
            measure  : benchmark[measure],
            group    : benchmark[group]}

        my_group = groups.setdefault(fixed_data, [])
        my_group.append(element)

    series_collection = []
    for el_list in groups.values():
        series = odict()
        for el in el_list:
            series.setdefault(el[group], []).append(el)
        series_collection.append(series)

    return [x for x in series_collection if len((x.values())[0]) >= min_series_length]


def mean(values):
    return min(values)
    #return sorted(values)[1:-1][(len(values)-2)/2]

def comp_function(keys, left, right):
    for key in keys:
        if key == 'index':
            return 0
        l, r = left[key], right[key]
        ordering = {
            'C > C' : 0,
            'J > C' : 1,
            'J > J' : 2,
            'C > J' : 3
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

def format_value(value):
    if type(value) == str:
        return '"{0}"'.format(value)
    else:
        return str(value)

def print_benchmarks(data, group=None, variable=None, measure=None, sort=None, min_series_width=None, measure_count=None):
    result = ""
    for k, series in enumerate(data):
        if len(series.keys()) < min_series_width:
            # there are not enough groups to display
            continue

        headers = []
        headers.append('"{v}"'.format(v=variable))
        headers.extend([format_value(value) for value in series.keys()])
        result += '"m:{measure} v:{variable} g:{group}" {headers}\n'.format(
            measure=measure,
            variable=variable,
            group=group, headers=" ".join(headers))

        var_value = None
        group_vals = []
        last_grp = series.values()[0]
        for idx in range(0, len(series.values()[0])):
            i = 0
            for key, grp in series.iteritems():
                if len(last_grp) != len(grp):
                    print 'error different lenght groups'
                    print last_grp
                    print grp
                    exit(1)
                
                if i == 0:
                    try:
                        var_value = grp[idx][variable]
                    except KeyError as e:
                        print variable
                    result += str(dict(grp[idx]['info'])['no']) + ' ' + format_value(var_value) + ' '
                else:
                    if var_value != grp[idx][variable]:
#                    debugdata.write(pp.pformat(series))
                        print 'Error: groups have different variables'
                        print 'expected', var_value, 'has', grp[idx][variable]
                        print 'key', key, 'k', k, 'series keys', series.keys()
                        exit(1)
                i += 1
                val = grp[idx][measure]
                if type(val) == str:
                    val = '"{0}"'.format(val)
                result += str(val) + ' '
                last_grp = grp

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

plot_simple_groups = """
set title '{title}'
unset label 1
plot for [I=3:{last_column}] '{filename}' index {index} using 2:I title columnhead with linespoints
"""

plot_named_columns = """
set title '{title}'
unset label 1
plot for [I=3:{last_column}] '{filename}' index {index} using I:xtic(2) title columnhead with linespoints
"""

plot_named_columns_vertical = """
set title '{title}'
unset label 1
set xtics rotate
plot for [I=3:{last_column}] '{filename}' index {index} using I:xtic(2) title columnhead with histogram
"""

def without(keys, d):
    if keys == None:
        return d
    dnew = odict()
    for key, val in d.iteritems():
        if key not in  keys:
            dnew[key] = val
    return dnew

def plot(
    benchmarks, gnuplot_script, plotpath, keys_to_remove=None, select_predicate=None,
    group=None, variable=None, measure=None, measure_count=None, title=None, num_groups=None,
    template=None, min_series_width=1):

    filename = os.path.join(plotpath, "plot-" + str(uuid.uuid4()) + ".data")
    filtered_benchmarks = [
        without(keys_to_remove, x)
        for x in benchmarks
        if select_predicate(x)]

    if len(filtered_benchmarks) == 0:
        print 'Error, no benchmarks for ', title
        exit(1)

    data = write_plotdata(plotpath, filename, filtered_benchmarks, {
         'group'         : group,
         'variable'      : variable, 
         'measure'       : measure,
         'measure_count' : measure_count,
         'min_series_width' : min_series_width})

    gnuplot_script.write(template.format(
       title = title, filename = filename, index = 0, last_column = 2 + num_groups))

def get_fixed_value(element, key):
    for k, v in element['fixed']:
        if k == key:
            return v
    return None

def all_values(data, key):
    directions = []
    return [get_fixed_value(plot.values()[0][0], key) for plot in data]

def plot_benchmarks(all_benchmarks, output, plotpath, gnuplotcommands, measure_count=None):
    f = open(gnuplotcommands, 'w')
    f.write(init_plots_gp.format(filename=output))

    custom_benchmarks = [bm for bm in all_benchmarks if bm['no'] == -1]
    benchmarks = [bm for bm in all_benchmarks if bm['no'] != -1]

    type_counts = ["parameter_type_{t}_count".format(t=tp) for tp in types]
    keys_to_remove = type_counts[:]
    keys_to_remove.extend(['parameter_type_count', 'single_type'])

    defaults = [benchmarks, f, plotpath]

    for i, ptype in enumerate(types):
        plot(
            benchmarks, f, plotpath,
            title = ptype,
            template = plot_simple_groups,
            keys_to_remove = keys_to_remove,
            select_predicate = lambda x: x['single_type'] in [ptype, 'any'],
            group = 'direction',
            variable = 'parameter_count',
            measure = 'response_time_millis',
            measure_count = measure_count,
            num_groups = 4)

    for direction in directions:
        plot(
            benchmarks, f, plotpath,
            title = 'Dynamic size: parameters, direction ' + direction,
            template = plot_simple_groups,
            keys_to_remove = type_counts,
            select_predicate = (
                lambda x: (
                    x['direction'] == direction and
                    x['has_reference_types'] == 1 and
                    x['single_type'] in reference_types and
                    x['parameter_count'] == 1)),
            group = 'single_type',
            variable = 'dynamic_size',
            measure = 'response_time_millis',
            measure_count = measure_count,
            num_groups = len(reference_types))

    for direction in directions:
        plot(
            benchmarks, f, plotpath,
            title = 'Dynamic size: return types, direction ' + direction,
            template = plot_simple_groups,
            keys_to_remove = type_counts,
            select_predicate = (
                lambda x: x['has_reference_types'] == 1
                and x['direction'] == direction 
                and x['return_type'] != 'void'),
            group = 'return_type',
            variable = 'dynamic_size',
            measure = 'response_time_millis',
            measure_count = measure_count,
            num_groups = len(reference_types))


    keys_to_remove = type_counts[:]
    keys_to_remove.append('has_reference_types')

    for direction in directions:
        plot(
            benchmarks, f, plotpath,
            template = plot_simple_groups,
            title = 'type grouping ' + direction,
            keys_to_remove = keys_to_remove,
            select_predicate = (
                lambda x: x['direction'] == direction),
            group = 'single_type',
            variable = 'parameter_count',
            measure = 'response_time_millis',
            measure_count = measure_count,
            num_groups = len(types))
    

    plot(
        benchmarks, f, plotpath,
        template = plot_named_columns,
        title = 'Return types',
        keys_to_remove = ['has_reference_types'],
        select_predicate = (
            lambda x: x['dynamic_size'] == 0 and
            x['return_type'] != 'void'),
        group = 'return_type',
        measure = 'response_time_millis',
        variable = 'direction',
        measure_count = measure_count,
        num_groups = len(types),
        min_series_width = 2)
    # had: sort 'response_time_millis', min_series_width: 2 , unused?

    plot(
        custom_benchmarks, f, plotpath,
        template = plot_simple_groups,
        title = 'Measuring overhead',
        keys_to_remove = [],
        select_predicate = (
            lambda x: 'fi.helsinki.cs.tituomin.nativebenchmark.benchmark.C2JOverhead' in x['class']),
        group = 'direction',
        measure = 'response_time_millis',
        variable = 'description',
        measure_count = measure_count,
        num_groups = 1)

    plot(
        custom_benchmarks, f, plotpath,
        measure_count=measure_count,
        template = plot_named_columns_vertical,
        title = 'Custom, non-dynamic',
        select_predicate = (
            lambda x: (x['dynamic_size'] == 0 and
            'fi.helsinki.cs.tituomin.nativebenchmark.benchmark.C2JOverhead' not in x['class'])),
        group = 'direction',
        num_groups = 1,
        measure = 'response_time_millis',
        variable = 'class')

#    dynamic_benchmarks = [x for x in benchmark]
        
def write_plotdata(path, filename, benchmarks, specs):
    plotdata = open(filename, 'w')
    data = extract_data(benchmarks, **specs)
    # debugdata.write(pp.pformat(data))    
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
                cpufreq = measurement.get('cpu-freq')
                if checksum and repetitions:
                        key = (checksum, repetitions, tool, cpufreq)
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
MEASUREMENT_PATH = '/cs/fs/home/tituomin/Ubuntu One/gradu/measurements'
#MEASUREMENT_PATH = '~/Ubuntu One/gradu/measurements'
DEVICE_PATH = '/sdcard/results'
PLOTPATH = '/tmp'
TOOL_NAMESPACE = 'fi.helsinki.cs.tituomin.nativebenchmark.measuringtool'

def sync_measurements(dev_path, host_path, filename, update=True):
    old_path = host_path + '/' + filename
    tmp_path = '/tmp/' + filename
    if not update and os.path.exists(old_path):
        print 'No sync necessary'
        return

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
    for measurement in benchmark_group:
        if measurement['tool'] == TOOL_NAMESPACE + '.LinuxPerfRecordTool':
            basename = "perfdata-{n}.zip"
        else:
            basename = "benchmarks-{n}.csv"
        filenames.append(
            basename.format(n=measurement['id']))

    files = []
    for filename in filenames:
        sync_measurements(DEVICE_PATH, MEASUREMENT_PATH, filename, update=False)
        files.append(open(os.path.join(MEASUREMENT_PATH, filename)))
    try:
        benchmarks = read_datafiles(files)
    finally:
        for f in files:
            f.close()

#    pp.pprint(benchmarks)

    measure_count = len(benchmark_group)
    plot_benchmarks(benchmarks, output, PLOTPATH, gnuplotoutput, measure_count=measure_count)
    exit(0)
    
