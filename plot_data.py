#!/usr/bin/python

from collections import OrderedDict as odict
from itertools import groupby
from subprocess import call
from sys import argv
import functools
import pprint
import re
import os
import shutil
import uuid

import numpy

from jni_types import primitive_type_definitions, object_type_definitions, array_types
from datafiles import read_datafiles, read_measurement_metadata
import analysis
from analysis import linear_fit
import gnuplot

primitive_types = [
    t['java']
    for t in primitive_type_definitions
]

reference_types = [
    '{p}.{t}'.format(p=t['package'], t=t['java'])
    for t in object_type_definitions + array_types.values()
    if t.get('package')
]

reference_types += [
    t['java']
    for t in array_types.itervalues()
    if not t.get('package')
]

types = reference_types + primitive_types

plot_axes = {
    'description': 'Operation count',
    'parameter_count' : 'Number of parameters',
    'dynamic_size' : 'Size of object',
    'direction' : 'Call direction',
    'id' : 'Name of benchmark'
    }
pp = pprint.PrettyPrinter(depth=10, indent=4)

debugdata = open('/tmp/debug.txt', 'w')

directions = [
    "%s > %s" % (fr, to) for fr, to in
    [('C', 'J'), ('J', 'C'), ('J', 'J'), ('C','C')]]

def preprocess_benchmarks(benchmarks, global_values):
    for b in benchmarks:
        add_derived_values(b)
        add_global_values(b, global_values)

def add_derived_values(benchmark):
    if benchmark['dynamic_size'] == None:
        benchmark['dynamic_variation'] = 0
        benchmark['dynamic_size'] = 0
    else:
        benchmark['dynamic_variation'] = 1

    single_type = None
    if (benchmark['parameter_count'] == 0):
        single_type = 'any'
    elif (benchmark['parameter_type_count'] == 1):
        for tp in types:
            if benchmark['parameter_type_{t}_count'.format(t=tp)] != None:
                single_type = tp
                break
    benchmark['single_type'] = single_type

def add_global_values(benchmark, global_values):
    for key, val in global_values.iteritems():
        if key not in benchmark or benchmark[key] == None:
            benchmark[key] = val
        elif key == 'multiplier' and benchmark[key] != None:
            benchmark[key] *= val


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
                        'fixed'    : dict((key, benchmark[key]) for key in controlled_variables),
                        'info'     : dict((key, benchmark[key]) for key in info),
                        'variable' : variable,
                        'measure'  : measure,
                        'group'    : group,
                        variable   : benchmark[variable],
                        measure    : benchmark[measure],
                        group      : benchmark[group]
                        }) for benchmark in plotgroups)

        benchmarks[i] = odict(
            sorted(((bms.values()[0][group], bms)
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

def comp_function(keys, left, right):
    for key in keys:
        if key not in left and key not in right:
            continue
        l, r = left[key], right[key]
        if l < r:
            return -1
        if l > r:
            return 1
    return 0        

def without(keys, d):
    if keys == None:
        return d
    return dict(((key, val) for key, val in d.iteritems() if key not in keys))

def plot(
    benchmarks, gnuplot_script, plotpath, metadata_file, keys_to_remove=None, select_predicate=None,
    group=None, variable=None, measure=None, title=None,
    style=None, min_series_width=1):

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
        'measure'          : measure}
    
    data = extract_data(filtered_benchmarks, **specs)

    for series in data:
        if len(series.keys()) < min_series_width:
            # there are not enough groups to display
            continue

        plot.page += 1
        axes_label = plot_axes.get(variable, '<unknown variable>')

        headers, rows = make_table(
            series, group, variable, measure, axes_label)

        gnuplot.output_plot(
            headers, rows, plotpath, gnuplot_script,
            title, specs, style, plot.page, axes_label)

        import textualtable
        metadata_file.write("\n\n{0} (Page {1})\n\n".format(title, plot.page))

        keyvalpairs = series.values()[0].values()[0]['fixed'].items() + [
            ('variable', axes_label),
            ('measure', measure),
            ('grouping', group)]

        for k,v in keyvalpairs:
             if v != None:
                 metadata_file.write("{k:<25} {v}\n".format(k=k, v=v))

        metadata_file.write("\n" + textualtable.make_textual_table(headers, rows))

        if variable != 'direction' and variable != 'id':
            x, polys, residuals = linear_fit(rows)

            fitted_curves = []
            for i, xval in enumerate(x):
                current = [xval]
                current.extend(rows[i][1:])
                current.extend([numpy.polyval(polys[j], xval) for j in range(0, len(rows[i]) - 1)])
                fitted_curves.append(current)

            plot.page += 1
            gnuplot.output_plot(
                headers + headers[1:], fitted_curves, plotpath, gnuplot_script,
                title, specs, 'fitted_lines', plot.page, axes_label)

            metadata_file.write("\nresiduals:\n" + textualtable.make_textual_table(headers[1:], [residuals]))
    return data

plot.page = 0

def make_table(series, group, variable, measure, axes_label):
    all_benchmark_variables_set = set()
    for bm_list in series.itervalues():
        all_benchmark_variables_set.update(bm_list.keys())

    all_benchmark_variables = sorted(list(all_benchmark_variables_set))

    rows = []

    headers = (
        [axes_label] +
        [k for k in series.iterkeys()]
    )
    
    for v in all_benchmark_variables:
        row = []
        row.append(v)
        for key, grp in series.iteritems():
            row.append(grp.get(v, {}).get(measure, None))
        rows.append(row)

    if variable == 'id':
        rows = sorted(rows, key=lambda x:x[1] or -1)

    return headers, rows
    

def plot_benchmarks(all_benchmarks, output, plotpath, gnuplotcommands, bid, metadata_file):
    gnuplot.init(gnuplotcommands, output, bid)

    #all_benchmarks = [x for x in all_benchmarks if x['repetitions'] == None and x['multiplier'] == None]

    custom_benchmarks = [bm for bm in all_benchmarks if bm['no'] == -1]
    benchmarks = [bm for bm in all_benchmarks if bm['no'] != -1]

    type_counts = ["parameter_type_{t}_count".format(t=tp) for tp in types]
    keys_to_remove = type_counts[:]
    keys_to_remove.extend(['parameter_type_count', 'single_type', 'dynamic_variation'])

    defaults = [benchmarks, gnuplotcommands, plotpath]

#    analysis.calculate_overheads()

    overhead_data = plot(
        custom_benchmarks, gnuplotcommands, plotpath, metadata_file,
        style = 'simple_groups',
        title = 'Measuring overhead',
        keys_to_remove = [],
        select_predicate = (
            lambda x: 'Overhead' in x['id']),
        group = 'direction',
        measure = 'response_time_millis',
        variable = 'description')

    for series in overhead_data:
        loop_id = series.itervalues().next().itervalues().next()['info']['id']

        if 'AllocOverhead' in loop_id:
            pass
        elif 'NormalOverhead' in loop_id:
            pass

    for i, ptype in enumerate(types):
        plot(
            benchmarks, gnuplotcommands, plotpath, metadata_file,
            title = ptype,
            style = 'simple_groups',
            keys_to_remove = keys_to_remove + ['dynamic_size'],
            select_predicate = lambda x: (
                x['single_type'] in [ptype, 'any'] and
                x['dynamic_size'] == 0),
            group = 'direction',
            variable = 'parameter_count',
            measure = 'response_time_millis')

    for direction in directions:
        plot(
            benchmarks, gnuplotcommands, plotpath, metadata_file,
            title = 'Dynamic size: parameters, direction ' + direction,
            style = 'simple_groups',
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
            benchmarks, gnuplotcommands, plotpath, metadata_file,
            title = 'Dynamic size: return types, direction ' + direction,
            style = 'simple_groups',
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
            benchmarks, gnuplotcommands, plotpath, metadata_file,
            style = 'simple_groups',
            title = 'Type grouping ' + direction,
            keys_to_remove = keys_to_remove,
            select_predicate = (
                lambda x: x['direction'] == direction),
            group = 'single_type',
            variable = 'parameter_count',
            measure = 'response_time_millis')
    

    plot(
        benchmarks, gnuplotcommands, plotpath, metadata_file,
        style = 'named_columns',
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

    for direction in directions:
        plot(
            custom_benchmarks, gnuplotcommands, plotpath, metadata_file,
            style = 'simple_groups',
            title = 'Custom, dynamic ' + direction,
            select_predicate = (
                lambda x: (x['direction'] == direction and
                           x['dynamic_variation'] == 1 and
                           'Overhead' not in x['id'])),
            group = 'id',
            measure = 'response_time_millis',
            variable = 'dynamic_size')

    plot(
        custom_benchmarks, gnuplotcommands, plotpath, metadata_file,
        style = 'histogram',
        title = 'Custom, non-dynamic',
        select_predicate = (
            lambda x: (
                x['dynamic_variation'] == 0 and
                'Overhead' not in x['id'])),
        group = 'direction',
        measure = 'response_time_millis',
        variable = 'id')

        

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
        benchmarks = read_datafiles(files)

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

    preprocess_benchmarks(benchmarks, global_values)
    plot_benchmarks(benchmarks, pdffilename, PLOTPATH, plotfile, benchmark_group_id, metadata_f)

    plotfile.flush()
    plotfile.close()
    call(["gnuplot", plotfile.name])
    if pdfviewer:
        call([pdfviewer, str(pdffilename)])
    print "Final plot", str(pdffilename)
    exit(0)
    
