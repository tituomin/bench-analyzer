#!/usr/bin/python

from sys import argv
from itertools import groupby
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

directions = [
    "%s > %s" % (fr, to) for fr, to in
    [('C', 'J'), ('J', 'C'), ('J', 'J'), ('C','C')]]

types = reference_types[:] + primitive_types

SEPARATOR = ','
NUMERICAL = '-?[0-9]+'
re_numerical = re.compile(NUMERICAL)

def explode(line):
    return line.split(SEPARATOR)

def value(string, key=None):
    if key == 'class':
        return string.split('.')[-1]
    if string == '-':
        return None
    if re_numerical.match(string):
        return int(string)
    else:
        return string

def add_derived_values(benchmark):
    single_type = None
    if (benchmark['parameter_count'] == 0):
        single_type = 'any'
    elif (benchmark['parameter_type_count'] == 1):
        for tp in types:
            if benchmark['parameter_type_{t}_count'.format(t=tp)] != None:
                single_type = tp
                break
    benchmark['single_type'] = single_type

    if benchmark['dynamic_size'] == None:
        benchmark['dynamic_variation'] = 0
        benchmark['dynamic_size'] = 0
    else:
        benchmark['dynamic_variation'] = 1

def add_global_values(benchmark, global_values):
    for key, val in global_values.iteritems():
        if key not in benchmark or benchmark[key] == None:
            benchmark[key] = val
        elif key == 'multiplier' and benchmark[key] != None:
            benchmark[key] *= val
    

def read_datafiles(files, global_values):
    print 'Reading from %s files' % len(files)
    benchmarks = []
    #-1: there is an empty field at the end...

    keys_with_values = set()
    all_keys = set()

    for i, f in enumerate(files):
        line = f.readline()
        labels = explode(line)[:-1]
        all_keys.update(labels)

        line = f.readline()
        lineno = 1
        while line != '':
            exploded_line = explode(line)[:-1]
            if len(labels) != len(exploded_line):
                print 'missing values', f.name, 'line', lineno, 'labels', len(labels), 'values', len(exploded_line)
                exit(1)

            benchmark = dict()

            for key, string in zip(labels, exploded_line):
                benchmark[key] = value(string, key=key)

                if value(string, key=key) != None:
                    keys_with_values.add(key)

            add_derived_values(benchmark)
            add_global_values(benchmark, global_values)

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

def extract_data(benchmarks,
                 group=None, variable=None, measure=None,
                 min_series_length=2, sort=None, min_series_width=None):

    # info == extra metadata not to be analyzed
    info = ['no', 'description']

    if 'class' in benchmarks[0]:
        info.append('class')
    if re.match('parameter_type_.+count', variable):
        info.append('parameter_count')
    if variable != 'id':
        info.append('id')

    # note: all the benchmarks have the same keyset
    all_keys = set(benchmarks[0].keys())

    # the actual keys of interest must have the least weight in sorting
    sort_last = [group, variable, measure] + info
    controlled_variables = all_keys - set(sort_last)
    sorted_keys = list(controlled_variables) + sort_last
 
    sorted_benchmarks = sorted(
        benchmarks,
        cmp=functools.partial(comp_function, sorted_keys))

    # 1. group benchmarks into a multi-dimensional list of the structure
    # compatible-measurements (controlled variables are equal)
    #     plots (list of individual data series ie. plots)
    #         multiple measurements ()
    benchmarks = group_by_keys(sorted_benchmarks, controlled_variables)
    for i, x  in enumerate(benchmarks):
        benchmarks[i] = group_by_keys(x, [group])
        for j, y in enumerate(benchmarks[i]):
            benchmarks[i][j] = group_by_keys(y, [variable])

    # 2. statistically combine multiple measurements
    # for the exact same benchmark and parameters,
    # and store information about the roles of keys

    for i, compatibles in enumerate(benchmarks):
        for j, plotgroups in enumerate(compatibles):
            for k, measured_values in enumerate(plotgroups):

                plotgroups[k] = aggregate_measurements(
                    measured_values, measure, stat_fun=min)

            compatibles[j] = odict(
                (benchmark[variable], {
                        'fixed'  : dict((key, benchmark[key]) for key in controlled_variables),
                        'info'   : dict((key, benchmark[key]) for key in info),
                        variable : benchmark[variable],
                        measure  : benchmark[measure],
                        group    : benchmark[group]
                        }) for benchmark in plotgroups)

        benchmarks[i] = odict(sorted(((bms.values()[0][group], bms)
                                      for bms in benchmarks[i]),
                                     key=lambda x:x[0]))

    return [x for x in benchmarks
            if len((x.values())[0]) >= min_series_length]

def group_by_keys(sorted_benchmarks, keyset):
    # todo make into generator?
    return [
        list(y) for x,y in groupby(
            sorted_benchmarks,
            key=lambda b: [b[k] for k in keyset])]
    
def aggregate_measurements(benchmarks, measure, stat_fun=min):
    values = []
    benchmark = None
    for benchmark in benchmarks:
        values.append(benchmark[measure])

    benchmark[measure] = stat_fun(values)

    if len(values) != benchmark['multiplier']:
        print "Error: expecting", benchmark['multiplier'], "measurements, got", len(values)
        debugdata.write(pp.pformat(list(benchmarks)))
        exit(1)

    return benchmark

def mean(values):
    return min(values)
    #return sorted(values)[1:-1][(len(values)-2)/2]

def comp_function(keys, left, right):
    for key in keys:
        if key not in left and key not in right:
            continue

        l, r = left[key], right[key]
        ordering = {
            'C > C' : 0,
            'J > C' : 1,
            'J > J' : 2,
            'C > J' : 3
            }

        if l in ordering.keys() and r in ordering.keys():
            l, r = ordering[l], ordering[r]

        if l < r:
            return -1
        # if l == None and r != None:
        #     return -1

        # if r == None and l != None:
        #     return 1
        if l > r:
            return 1
    return 0        

def format_value(value):
    if type(value) == str:
        return '"{0}"'.format(value)
    else:
        return str(value)

def print_benchmarks(series, title, group=None, variable=None, measure=None, sort=None, min_series_width=None):
    all_benchmark_variables_set = set()
    for bm_list in series.itervalues():
        all_benchmark_variables_set.update(bm_list.keys())

    all_benchmark_variables = sorted(list(all_benchmark_variables_set))

    rows = []
    for v in all_benchmark_variables:
        row = []
        row.append('0')
        row.append(format_value(v))
        for key, grp in series.iteritems():
            row.append(format_value(grp.get(v, {}).get(measure, -500)))
        rows.append(row)

    if variable == 'id':
        rows = sorted(rows, key=lambda x:int(x[2]))

    headers = " ".join(
        ['"{0}"'.format(variable)] +
        [format_value(value) for value in series.iterkeys()])

    result = '#{0}\n"m:{0} v:{1} g:{2}" {3}\n'.format(
        title, measure, variable, group, headers)

    for row in rows:
        result += ' '.join(row)
        result += '\n'
    result += '\n\n'

    return result

init_plots_gp = """
set terminal pdfcairo size 32cm,18cm
set output '{filename}'
set key outside
set size 1, 0.95
set xlabel "Number of parameters"
set ylabel "Response time (ms)"
set label 1 "{bid}" at graph 0.01, graph 1.1
"""

plot_simple_groups = """
set title '{title}'
plot for [I=3:{last_column}] '{filename}' index {index} using 2:I title columnhead with linespoints
"""

plot_named_columns = """
set title '{title}'
plot for [I=3:{last_column}] '{filename}' index {index} using I:xtic(2) title columnhead with linespoints
"""

plot_named_columns_vertical = """
set title '{title}'
set xtics rotate
#set boxwidth 20
#set style fill solid border lc rgbcolor "black"
set style data histograms
set style histogram clustered
set style fill solid 1.0 border lt -1
plot for [I=3:{last_column}] '{filename}' index {index} using I:xtic(2) title columnhead with histogram
"""

def without(keys, d):
    if keys == None:
        return d
    return dict(((key, val) for key, val in d.iteritems() if key not in keys))

def plot(
    benchmarks, gnuplot_script, plotpath, keys_to_remove=None, select_predicate=None,
    group=None, variable=None, measure=None, title=None,
    template=None, min_series_width=1):

    print 'Plotting', title

    filtered_benchmarks = [
        without(keys_to_remove, x)
        for x in benchmarks
        if select_predicate(x)]

    variables = set([benchmark[variable] for benchmark in filtered_benchmarks])
    if len(variables) < 2:
        print 'Skipping plot without enough data variables\n'
        return

    if len(filtered_benchmarks) == 0:
        print 'Error, no benchmarks for', title
        exit(1)

    specs = {
        'group'            : group,
        'variable'         : variable, 
        'measure'          : measure,
        'min_series_width' : min_series_width}
    
    data = extract_data(filtered_benchmarks, **specs)

    for series in data:
        if len(series.keys()) < min_series_width:
            # there are not enough groups to display
            continue

        filename = os.path.join(plotpath, "plot-" + str(uuid.uuid4()) + ".data")
        plotdata = open(filename, 'w')
        # debugdata.write(pp.pformat(data))
        plotdata.write(print_benchmarks(series, title, **specs))

        gnuplot_script.write(template.format(
           title = title, filename = filename, index = 0, last_column = 2 + len(series)))

def get_fixed_value(element, key):
    for k, v in element['fixed']:
        if k == key:
            return v
    return None

def all_values(data, key):
    directions = []
    return [get_fixed_value(plot.values()[0][0], key) for plot in data]

def plot_benchmarks(all_benchmarks, output, plotpath, gnuplotcommands, bid):
    gnuplotcommands.write(init_plots_gp.format(filename=output, bid=bid))

    #all_benchmarks = [x for x in all_benchmarks if x['repetitions'] == None and x['multiplier'] == None]

    custom_benchmarks = [bm for bm in all_benchmarks if bm['no'] == -1]
    benchmarks = [bm for bm in all_benchmarks if bm['no'] != -1]

    type_counts = ["parameter_type_{t}_count".format(t=tp) for tp in types]
    keys_to_remove = type_counts[:]
    keys_to_remove.extend(['parameter_type_count', 'single_type', 'dynamic_variation'])

    defaults = [benchmarks, gnuplotcommands, plotpath]

    for i, ptype in enumerate(types):
        plot(
            benchmarks, gnuplotcommands, plotpath,
            title = ptype,
            template = plot_simple_groups,
            keys_to_remove = keys_to_remove + ['dynamic_size'],
            select_predicate = lambda x: (
                x['single_type'] in [ptype, 'any'] and
                x['dynamic_size'] == 0),
            group = 'direction',
            variable = 'parameter_count',
            measure = 'response_time_millis')

    for direction in directions:
        plot(
            benchmarks, gnuplotcommands, plotpath,
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
            measure = 'response_time_millis')

    for direction in directions:
        plot(
            benchmarks, gnuplotcommands, plotpath,
            title = 'Dynamic size: return types, direction ' + direction,
            template = plot_simple_groups,
            keys_to_remove = type_counts,
            select_predicate = (
                lambda x: x['has_reference_types'] == 1
                and x['direction'] == direction 
                and x['return_type'] != 'void'),
            group = 'return_type',
            variable = 'dynamic_size',
            measure = 'response_time_millis')


    keys_to_remove = type_counts[:]
    keys_to_remove.append('has_reference_types')
    keys_to_remove.append('dynamic_variation')

    for direction in directions:
        plot(
            benchmarks, gnuplotcommands, plotpath,
            template = plot_simple_groups,
            title = 'Type grouping ' + direction,
            keys_to_remove = keys_to_remove,
            select_predicate = (
                lambda x: x['direction'] == direction),
            group = 'single_type',
            variable = 'parameter_count',
            measure = 'response_time_millis')
    

    plot(
        benchmarks, gnuplotcommands, plotpath,
        template = plot_named_columns,
        title = 'Return types',
        keys_to_remove = ['has_reference_types', 'dynamic_variation'],
        select_predicate = (
            lambda x: x['dynamic_size'] == 0 and
            x['return_type'] != 'void'),
        group = 'return_type',
        measure = 'response_time_millis',
        variable = 'direction',
        min_series_width = 2)
    # had: sort 'response_time_millis', min_series_width: 2 , unused?

    plot(
        custom_benchmarks, gnuplotcommands, plotpath,
        template = plot_simple_groups,
        title = 'Measuring overhead',
        keys_to_remove = [],
        select_predicate = (
            lambda x: 'Overhead' in x['id']),
        group = 'direction',
        measure = 'response_time_millis',
        variable = 'description')

    for direction in directions:
        plot(
            custom_benchmarks, gnuplotcommands, plotpath,
            template = plot_simple_groups,
            title = 'Custom, dynamic ' + direction,
            select_predicate = (
                lambda x: (x['direction'] == direction and
                           x['dynamic_variation'] == 1 and
                           'Overhead' not in x['id'])),
            group = 'id',
            measure = 'response_time_millis',
            variable = 'dynamic_size')

    plot(
        custom_benchmarks, gnuplotcommands, plotpath,
        template = plot_named_columns_vertical,
        title = 'Custom, non-dynamic',
        select_predicate = (
            lambda x: (
                x['dynamic_variation'] == 0 and
                'Overhead' not in x['id'])),
        group = 'direction',
        measure = 'response_time_millis',
        variable = 'id')

        
def write_plotdata(path, filename, data, specs):
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
                revision = measurement.get('code-revision')
                repetitions = measurement.get('repetitions')
                tool = measurement.get('tool')
                cpufreq = measurement.get('cpu-freq')
                if revision and repetitions:
                        key = (revision, repetitions, tool, cpufreq)
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
    if len(argv) < 4 or len(argv) > 5:
        print "\n    Usage: python plot_data.py input_path output_path limit [pdfviewer]\n"
        exit(1)

    measurement_path = argv[1]
    output_path = argv[2]
    limit = argv[3]
    if len(argv) == 5:
        pdfviewer = argv[4]
    else:
        pdfviewer = None

    sync_measurements(DEVICE_PATH, measurement_path, MEASUREMENT_FILE)

    f = open(os.path.join(measurement_path, MEASUREMENT_FILE))

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

    try:
        response = raw_input("Choose set 1-{last} >> ".format(last=i-1))
    except EOFError:
        print 'Exiting.'
        exit(1)
    
    benchmark_group = limited_measurements[int(response) - 1]

    filenames = []
    ids = []
    for measurement in benchmark_group:
        if measurement['tool'] == TOOL_NAMESPACE + '.LinuxPerfRecordTool':
            basename = "perfdata-{n}.zip"
        else:
            basename = "benchmarks-{n}.csv"
        filenames.append(
            basename.format(n=measurement['id']))
        ids.append(measurement['id'])

    files = []
    for filename in filenames:
        sync_measurements(DEVICE_PATH, measurement_path, filename, update=False)
        files.append(open(os.path.join(measurement_path, filename)))

    first_measurement = benchmark_group[0]

    global_values = {
        'repetitions': first_measurement['repetitions'],
        'multiplier' : len(benchmark_group)
        }

    try:
        if first_measurement['tool'] == TOOL_NAMESPACE + '.LinuxPerfRecordTool':
            print 'Nothing to be done for perf data. Exiting.'
            exit(0)
        benchmarks = read_datafiles(files, global_values)

    finally:
        for f in files:
            f.close()

#    pp.pprint(benchmarks)

    benchmark_group_id = str(uuid.uuid4())
    pdffilename = os.path.join(output_path, 'plot-{0}.pdf'.format(benchmark_group_id))
    plotfilename = 'plot-{0}.gp'.format(benchmark_group_id)
    plotfile = open(os.path.join(output_path, plotfilename), 'w')
    metadata_f = open(os.path.join(output_path, 'plot-{0}-metadata.txt'.format(benchmark_group_id)), 'w')
    metadata_f.write("id: {0}\n".format(benchmark_group_id))
    metadata_f.write("measurements: {0}\n".format(" ".join(ids)))

    plot_benchmarks(benchmarks, pdffilename, PLOTPATH, plotfile, benchmark_group_id)
    plotfile.flush()
    plotfile.close()
    call(["gnuplot", plotfile.name])
    if pdfviewer:
        call([pdfviewer, str(pdffilename)])
    print "Final plot", str(pdffilename)
    exit(0)
    
