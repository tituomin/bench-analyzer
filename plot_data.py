#!/usr/bin/python
# -*- coding: utf-8 -*-

from collections import OrderedDict as odict
from itertools import groupby
from subprocess import call
from sys import argv
import functools
import pprint
import re
import os
import sys
import shutil
import uuid

import glob
import zipfile

import numpy
from numpy import array

from jni_types import primitive_type_definitions, object_type_definitions, array_types
from datafiles import read_datafiles, read_measurement_metadata
import analysis
from analysis import linear_fit, estimate_measuring_overhead
import gnuplot
import textualtable

FNULL = None

primitive_types = [
    t['java']
    for t in primitive_type_definitions
]

reference_types = [
    t['java']
    for t in array_types.itervalues()
]

reference_types.extend([
    t['java']
    for t in object_type_definitions
])

types = reference_types + primitive_types

plot_axes = {
    'description': 'operaatioiden määrä',
    'parameter_count': 'kutsuparametrien määrä',
    'dynamic_size': 'kohteen koko',
    'direction': 'kutsusuunta',
    'id': 'nimi'
}
pp = pprint.PrettyPrinter(depth=10, indent=4)

debugdata = open('/tmp/debug.txt', 'w')

def format_direction(fr, to, latex):
    if fr == 'J':
        fr = 'Java'
    if to == 'J':
        to = 'Java'
    if latex:
        SEPARATOR = '$\\\\rightarrow$'
    else:
        SEPARATOR = ' > '
    return "%s%s%s" % (fr, SEPARATOR, to)

DIRECTIONS = [('C', 'J'), ('J', 'C'), ('J', 'J'), ('C', 'C')]

def preprocess_benchmarks(benchmarks, global_values, latex=None):
    # For allocating benchmarks, the repetition count for individual benchmarks
    # come from the datafile. For non-allocating, it is a global value.
    keys = set([key for b in benchmarks for key in b.keys()])
    if 'repetitions' in keys:
        benchmarks = [b for b in benchmarks if b['repetitions'] is not None]
    for b in benchmarks:
        add_derived_values(b, latex=latex)
        add_global_values(b, global_values)
    return benchmarks

def add_derived_values(benchmark, latex=None):
    # migration - todo - remove
    if benchmark.get('response_time_millis') != None:
        benchmark['response_time'] = benchmark.get('response_time_millis')
        benchmark['time_unit'] = 'milliseconds'
        del benchmark['response_time_millis']
    if benchmark.get('dynamic_size') == None:
        benchmark['dynamic_variation'] = 0
        benchmark['dynamic_size'] = 0
    else:
        benchmark['dynamic_variation'] = 1
    if benchmark['no'] == -1:
        # Custom benchmark, do some name mapping:
        bid = benchmark['id']
        rename = True
        if bid == 'CopyUnicode':
            bid = 'GetStringRegion'
        elif bid == 'CopyUTF':
            bid = 'GetStringRegionUTF'
        elif bid == 'StringLength':
            bid = 'GetStringLength'
        elif bid == 'StringLengthUTF':
            bid = 'GetStringUTFLength'
        elif bid == 'ReadUnicode':
            bid = 'ReadString'
        elif bid == 'ReadUnicodeCritical':
            bid = 'ReadStringCritical'
        elif bid == 'ReadUTF':
            bid = 'ReadStringUTF'
        elif bid == 'ReadUtf':
            bid = 'ReadStringUTF'
        elif bid == 'ReadObjectArrayElement':
            bid = 'GetObjectArrayElement'
        elif bid == 'WriteObjectArrayElement':
            bid = 'SetObjectArrayElement'
        else:
            rename = False
        if rename:
            benchmark['id'] = bid

    single_type = None
    if (benchmark.get('parameter_count') == 0):
        single_type = 'any'
    elif (benchmark.get('parameter_type_count') == 1):
        for tp in types:
            if benchmark.get('parameter_type_{t}_count'.format(t=tp)) != None:
                single_type = tp
                break
    benchmark['direction'] = format_direction(benchmark['from'], benchmark['to'], latex)
    benchmark['single_type'] = single_type
    if 'Nio' in benchmark['id']:
        benchmark['nio'] = True
    else:
        benchmark['nio'] = False

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
    info = ['no', 'from', 'to', 'lineno', 'start', 'end']

    if 'class' in benchmarks[0]:
        info.append('class')
    if 'description' in benchmarks[0]:
        info.append('description')
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

    # 1. group benchmarks into a multi-dimensional list
    #    with the following structure:
    #    - compatible-measurements (controlled variables are equal)
    #      - plots (list of individual data series ie. plots)
    #        - multiple measurements ()
    benchmarks = group_by_keys(sorted_benchmarks, controlled_variables)
    for i, x in enumerate(benchmarks):
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
                    'fixed': dict((key, benchmark[key]) for key in controlled_variables),
                    'info': dict((key, benchmark[key]) for key in info),
                    'variable': variable,
                    'measure': measure,
                    'group': group,
                    variable: benchmark[variable],
                    measure: benchmark[measure],
                    group: benchmark[group]
                }) for benchmark in plotgroups)

        benchmarks[i] = odict(
            sorted(((bms.values()[0][group], bms)
                    for bms in benchmarks[i]),
                   key=lambda x: x[0]))

    return [x for x in benchmarks
            if len((x.values())[0]) >= min_series_length]


def group_by_keys(sorted_benchmarks, keyset):
    # todo make into generator?
    return [
        list(y) for x, y in groupby(
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
        benchmarks, gnuplot_script, plotpath, metadata_file,
        keys_to_remove=None, select_predicate=None,
        group=None, variable=None, measure=None,
        title=None, style=None, min_series_width=1,
        key_placement='inside top left',
        identifier=None,
        revision=None, checksum=None, output='pdf'):

    if len(benchmarks) > 0 and benchmarks[0].get('is_allocating'):
        identifier += '-alloc'
    if len(benchmarks) > 0:
        reps = benchmarks[0].get('repetitions')

    filtered_benchmarks = [
        without(keys_to_remove, x)
        for x in benchmarks
        if select_predicate(x)]

    variables = set([benchmark[variable] for benchmark in filtered_benchmarks])

    if len(variables) < 2:
        print 'Skipping plot without enough data variables', title
        return

    if len(filtered_benchmarks) == 0:
        print 'Error, no benchmarks for', title
        exit(1)

    print 'Plotting', title

    specs = {
        'group': group,
        'variable': variable,
        'measure': measure}

    data = extract_data(filtered_benchmarks, **specs)

    index = -1

    data_len = len([s for s in data if len(s.keys()) >= min_series_width])
    for series in data:
        if len(series.keys()) < min_series_width:
            # there are not enough groups to display
            continue
        index += 1

        plot.page += 1
        axes_label = plot_axes.get(variable, '<unknown variable>')

        headers, rows = make_table(
            series, group, variable, measure, axes_label)

        assert identifier is not None
        id_suffix = ""
        if data_len > 1:
            id_suffix = "-{}".format(index)

        gnuplot.output_plot(
            headers, rows, plotpath, gnuplot_script,
            title, specs, style, plot.page, identifier + id_suffix, axes_label, output=output,
            key_placement=key_placement, reps=reps
        )

        metadata_file.write("\n\n{0}\n{1}\n\n".format(title, identifier + id_suffix))

        keyvalpairs = series.values()[0].values()[0]['fixed'].items() + [
            ('variable', axes_label),
            ('measure', measure),
            ('grouping', group)]

        for k, v in keyvalpairs:
            if v != None:
                metadata_file.write("{k:<25} {v}\n".format(k=k, v=v))

        metadata_file.write(
            "\n" + textualtable.make_textual_table(headers, rows))

        id_headers, id_rows = make_table(
            series, group, variable, 'class', axes_label)

        def make_id(variable_value, item, variable):
            ret = "/".join([revision, item or '-'])
            if variable == 'dynamic_size':
                ret += "/" + str(variable_value)
            return ret

        id_rows = [
            [row[0]] +
            [make_id(row[0], item, variable) for item in row[1:]]
            for row in id_rows]

        ttable = textualtable.make_textual_table(id_headers, id_rows)
        metadata_file.write("\n" + ttable)

        if variable != 'direction' and variable != 'id':
            x, polys, residuals = linear_fit(rows)

            fitted_curves = []
            for i, xval in enumerate(x):
                current = [xval]
                current.extend(rows[i][1:])
                current.extend([numpy.polyval(polys[j], xval)
                                for j in range(0, len(rows[i]) - 1)])
                fitted_curves.append(current)

            plot.page += 1
            gnuplot.output_plot(
                headers + headers[1:], fitted_curves, plotpath, gnuplot_script,
                title, specs, 'fitted_lines', plot.page, identifier + id_suffix + '-fit', axes_label, output=output, reps=reps)

            def simplified_function(poly):
                return "{:.3g} * x {:+.3g}".format(poly[0], poly[1])
            metadata_file.write(
                "\npolynomial:\n" + textualtable.make_vertical_textual_table(headers[1:], [map(simplified_function, polys)]))
            metadata_file.write(
                "\nresiduals:\n" + textualtable.make_vertical_textual_table(headers[1:], [residuals]))
            metadata_file.write(
                "\nslope:\n" + textualtable.make_vertical_textual_table(headers[1:], [map(lambda p: p[0], polys)]))
            metadata_file.write(
                "\nintercept:\n" + textualtable.make_vertical_textual_table(headers[1:], [map(lambda p: p[1], polys)]))
    return data

plot.page = 0

def convert_to_seconds(value):
    if type(value) == int:
        strval = str(value)
        if convert_to_seconds == False:
            return strval
        strval = strval.zfill(10)
        strlen = len(strval)
        return float("{}.{}".format(
            strval[0:strlen-9],
            strval[strlen-9:]))
    return value

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
            val = grp.get(v, {}).get(measure, None)
            if val is None:
                val = grp.get(v, {}).get('info', {}).get(measure, None)
            if measure == 'response_time':
                val = convert_to_seconds(val)
            row.append(val)
        rows.append(row)

    if variable == 'id':
        rows = sorted(rows, key=lambda x: x[1] or -1)

    return headers, rows


def binned_value(minimum, width, value):
    return width * (int(value - minimum) / int(width)) + minimum


def plot_distributions(all_benchmarks, output, plotpath, gnuplotcommands, bid, metadata_file, plot_type=None, latex=None, **kwargs):

    output_type = 'screen'
    if plot_type != 'animate':
        output_type = 'pdf'

    gnuplot.init(gnuplotcommands, output, bid, output_type=output_type)
    measure = 'response_time'

    keyset = set(all_benchmarks[0].keys()) - \
        set([measure, 'lineno', 'start', 'end'])
    comparison_function = functools.partial(comp_function, keyset)
    sorted_benchmarks = sorted(all_benchmarks, cmp=comparison_function)

    for group in group_by_keys(sorted_benchmarks, keyset):
        if plot_type != None:
            keyf = lambda x: x['lineno']
        else:
            keyf = lambda x: x[measure]

        frame_count = 1
        if plot_type != None:
            frame_count = 256

        current_frame = frame_count
        all_values = [b[measure] for b in sorted(group, key=keyf)]
        while current_frame > 0:

            if current_frame == frame_count:
                frame_ratio = 1
            else:
                frame_ratio = float(current_frame) / frame_count
            values = array(all_values[0:int(frame_ratio * len(all_values))])

            bin_width = 500
            min_x = numpy.amin(all_values)
            max_x = numpy.amax(all_values)

            bin_no = (max_x - min_x) / bin_width

            hgram, bin_edges = numpy.histogram(values, bins=max(bin_no, 10))

            mode = bin_edges[numpy.argmax(hgram)]
            min_x = mode - 100000
            max_x = mode + 100000

            if current_frame == frame_count:
                metadata_file.write(
                    'Direction {0}\n'.format(group[0]['direction']))
                # for val in sorted(counts.itervalues(), key=lambda x:-x['count'])[0:20]:
                #     metadata_file.write("{:>12} {:>12} {:>12}\n".format(
                #             val['limit'], val['percent'], val['count']))
                # metadata_file.write("---\n")
                # for val in sorted(counts.itervalues(), key=lambda x:x['limit']):
                #     metadata_file.write("{:>12} {:>12} {:>12}\n".format(
                #             val['limit'], val['percent'], val['count']))

                gnuplotcommands.write(
                    gnuplot.templates['binned_init'].format(
                        title='%s %s' % (group[0]['id'], group[
                                         0]['direction']),
                        binwidth=bin_edges[1] - bin_edges[0], min_x=min_x, max_x=max_x,
                        max_y=numpy.max(hgram)))

                if plot_type == 'animate':
                    gnuplotcommands.write('pause -1\n')

                elif plot_type == 'gradient':
                    gnuplotcommands.write("set multiplot\n")

            current_frame -= 1

            if plot_type == None:
                gnuplotcommands.write(
                    gnuplot.templates['binned_frame'].format(
                        datapoints='', color='#000033',
                        values='\n'.join(['{} {} {}'.format(val, count, val) for val, count in zip(bin_edges, hgram)])))

            elif plot_type == 'gradient':
                gnuplotcommands.write(
                    gnuplot.templates['binned_frame'].format(
                        datapoints='',
                        color=gnuplot.hex_color_gradient(
                            (125, 0, 0), (255, 255, 0), 1 - frame_ratio),
                        values='\n'.join(['{} {} {}'.format(val, count, val) for val, count in zip(bin_edges, hgram)])))

        gnuplotcommands.write("set xtics\n")
        gnuplotcommands.write("set ytics\n")


def plot_benchmarks(
        all_benchmarks, output, plotpath, gnuplotcommands, bid, metadata_file,
        plot_type=None, revision=None, checksum=None, latex=None):

    output_type = 'pdf'
    if latex == 'plotlatex':
        output_type = 'latex'
    elif latex == 'plotsvg':
        output_type = 'svg'

    gnuplot.init(gnuplotcommands, output, bid, output_type=output_type)

    #all_benchmarks = [x for x in all_benchmarks if x['repetitions'] == None and x['multiplier'] == None]

    type_counts = ["parameter_type_{t}_count".format(t=tp) for tp in types]
    keys_to_remove = type_counts[:]
    keys_to_remove.extend(
        ['parameter_type_count', 'single_type', 'dynamic_variation'])

    benchmarks = [bm for bm in all_benchmarks if bm['no'] != -1]
    defaults = [benchmarks, gnuplotcommands, plotpath]

#    analysis.calculate_overheads()
    overhead_estimates = {}
    overhead_benchmarks = [
        bm for bm in all_benchmarks
        if bm['no'] == -1 and 'Overhead' in bm ['id']]
    for loop_type in ['AllocOverhead', 'NormalOverhead']:
        for from_lang in ['C', 'J']:
            language_name = from_lang
            if language_name == 'J': language_name = 'Java'
            overhead_estimates[from_lang] = {}
            overhead_data = plot(
                overhead_benchmarks, gnuplotcommands, plotpath, metadata_file,
                style='simple_groups',
                key_placement=None,
                title='Mittauksen perusrasite ({})'.format(language_name),
                identifier='{}-{}'.format(loop_type.lower(), from_lang.lower()),
                keys_to_remove=[],
                select_predicate=(
                        lambda x: x['from'] == from_lang and loop_type in x['id']),
                group='from',
                measure='response_time',
                variable='description',
                revision=revision,
                checksum=checksum,
                output=output_type)

            if overhead_data == None:
                continue
            if len(overhead_data) > 1:
                print 'Error, more loop types than expected.', len(overhead_data)
                exit(1)

            series = overhead_data[0]
            headers, rows = make_table(series,
                                       'from',
                                       'description',
                                       'response_time',
                                       'workload')
            est = estimate_measuring_overhead(rows[1:])
            overhead_estimates[from_lang][loop_type] = est[0]
            metadata_file.write('Overhead ' + from_lang + ' ' + str(est[0]))

    for i, ptype in enumerate(types):
        plot(
            benchmarks, gnuplotcommands, plotpath, metadata_file,
            title='{}-tyyppiset kutsuparametrit'.format(ptype),
            identifier='basic-call-{}'.format(ptype),
            style='simple_groups',
            keys_to_remove=keys_to_remove + ['dynamic_size'] + ['has_reference_types'],
            select_predicate=lambda x: (
                x['single_type'] in [ptype, 'any'] and
                x['dynamic_size'] == 0),
            group='direction',
            variable='parameter_count',
            measure='response_time',
            revision=revision, checksum=checksum, output=output_type)

    for fr, to in DIRECTIONS:
        direction = format_direction(fr, to, latex)
        plot(
            benchmarks, gnuplotcommands, plotpath, metadata_file,
            title='Vaihteleva argumentin koko kutsusuunnassa ' + direction,
            identifier='variable-argument-size-{}-{}'.format(fr.lower(), to.lower()),
            style='simple_groups',
            keys_to_remove=type_counts,
            select_predicate=(
                lambda x: (
                    x['direction'] == direction and
                    x['has_reference_types'] == 1 and
                    x['single_type'] in reference_types and
                    x['parameter_count'] == 1)),
            group='single_type',
            variable='dynamic_size',
            measure='response_time',
            revision=revision, checksum=checksum, output=output_type)

    for fr, to in DIRECTIONS:
        direction = format_direction(fr, to, latex)
        plot(
            benchmarks, gnuplotcommands, plotpath, metadata_file,
            title='Vaihteleva paluuarvon koko kutsusuunnassa ' + direction,
            identifier='variable-return-value-size-{}-{}'.format(fr.lower(), to.lower()),
            style='simple_groups',
            keys_to_remove=type_counts,
            select_predicate=(
                lambda x: x['has_reference_types'] == 1
                and x['direction'] == direction
                and x['return_type'] != 'void'),
            group='return_type',
            variable='dynamic_size',
            measure='response_time',
            revision=revision, checksum=checksum, output=output_type)

    keys_to_remove = type_counts[:]
    keys_to_remove.append('has_reference_types')
    keys_to_remove.append('dynamic_variation')

    for fr, to in DIRECTIONS:
        direction = format_direction(fr, to, latex)
        plot(
            benchmarks, gnuplotcommands, plotpath, metadata_file,
            style='simple_groups',
            title='Parametrityyppien vertailu ' + direction,
            identifier='basic-call-all-types-{}-{}'.format(fr.lower(), to.lower()),
            keys_to_remove=keys_to_remove,
            select_predicate=(
                lambda x: x['direction'] == direction),
            group='single_type',
            variable='parameter_count',
            measure='response_time',
            revision=revision, checksum=checksum, output=output_type)

    plot(
        benchmarks, gnuplotcommands, plotpath, metadata_file,
        style='named_columns',
        title='Paluuarvon tyypit',
        identifier='return-value-types',
        keys_to_remove=['has_reference_types', 'dynamic_variation'],
        select_predicate=(
            lambda x: x['dynamic_size'] == 0 and
            x['return_type'] != 'void'),
        group='return_type',
        measure='response_time',
        variable='direction',
        min_series_width=2,
        revision=revision, checksum=checksum, output=output_type)
    # had: sort 'response_time', min_series_width: 2 , unused?

    def utf(b):
        return 'UTF' in b['id'] or 'Utf' in b['id']

    filters = {
        'utf': utf,
        'arrayregion': lambda x: 'ArrayRegion' in x['id'],
        'bytebufferview': lambda x: 'ByteBufferView' in x['id'],
        'unicode': lambda b: not utf(b) and 'String' in b['id'],
        'arrayelements': (lambda x:
                          'ArrayElements' in x['id'] or
                          'ArrayLength' in x['id'] or
                          'ReadPrimitive' in x['id']),
    }
    def uncategorized(x):
        for f in filters.values():
            if f(x):
                return False
        return True

    benchmarks = {}
    for key, f in filters.iteritems():
        benchmarks[key] = [
            bm for bm in all_benchmarks
            if bm['no'] == -1 and f(bm)]

    benchmarks['uncategorized'] = [
        bm for bm in all_benchmarks
        if bm['no'] == -1 and 'Overhead' not in bm['id'] and uncategorized(bm)]

    custom_benchmarks = benchmarks['uncategorized']

    for fr, to in DIRECTIONS:
        direction = format_direction(fr, to, latex)
        plot(
            custom_benchmarks, gnuplotcommands, plotpath, metadata_file,
            style='simple_groups',
            title='Erityiskutsut suunnassa ' + direction,
            identifier='special-calls-{}-{}'.format(fr.lower(), to.lower()),
            select_predicate=(
                lambda x: (x['direction'] == direction and
                           x['dynamic_variation'] == 1)),
            group='id',
            measure='response_time',
            variable='dynamic_size',
            revision=revision, checksum=checksum, output=output_type)

        plot(
            benchmarks['arrayregion'], gnuplotcommands, plotpath, metadata_file,
            style='simple_groups',
            title='Erityiskutsut suunnassa ' + direction,
            identifier='special-calls-arrayregion-{}-{}'.format(fr.lower(), to.lower()),
            select_predicate=(
                lambda x: (x['direction'] == direction and
                           x['dynamic_variation'] == 1)),
            group='id',
            measure='response_time',
            variable='dynamic_size',
            revision=revision, checksum=checksum, output=output_type)

        plot(
            benchmarks['arrayelements'], gnuplotcommands, plotpath, metadata_file,
            style='simple_groups',
            title='Erityiskutsut suunnassa ' + direction,
            identifier='special-calls-arrayelements-{}-{}'.format(fr.lower(), to.lower()),
            select_predicate=(
                lambda x: (x['direction'] == direction and
                           x['dynamic_variation'] == 1)),
            group='id',
            measure='response_time',
            variable='dynamic_size',
            revision=revision, checksum=checksum, output=output_type)

        plot(
            benchmarks['utf'], gnuplotcommands, plotpath, metadata_file,
            style='simple_groups',
            title='UTF-merkkijonot suunnassa ' + direction,
            identifier='special-calls-utf-{}-{}'.format(fr.lower(), to.lower()),
            select_predicate=(
                lambda x: (x['direction'] == direction and
                           x['dynamic_variation'] == 1)),
            group='id',
            measure='response_time',
            variable='dynamic_size',
            revision=revision, checksum=checksum, output=output_type)

        plot(
            benchmarks['unicode'], gnuplotcommands, plotpath, metadata_file,
            style='simple_groups',
            key_placement='inside bottom left',
            title='Unicode-merkkijonot suunnassa ' + direction,
            identifier='special-calls-unicode-{}-{}'.format(fr.lower(), to.lower()),
            select_predicate=(
                lambda x: (x['direction'] == direction and
                           x['dynamic_variation'] == 1)),
            group='id',
            measure='response_time',
            variable='dynamic_size',
            revision=revision, checksum=checksum, output=output_type)

        plot(
            benchmarks['bytebufferview'], gnuplotcommands, plotpath, metadata_file,
            style='simple_groups',
            title='Erityiskutsut suunnassa ' + direction,
            identifier='special-calls-bytebufferview-{}-{}'.format(fr.lower(), to.lower()),
            select_predicate=(
                lambda x: (x['direction'] == direction and
                           x['dynamic_variation'] == 1 and
                           'Bulk' not in x['id'])),
            group='id',
            measure='response_time',
            variable='dynamic_size',
            revision=revision, checksum=checksum, output=output_type)

        plot(
            benchmarks['bytebufferview'], gnuplotcommands, plotpath, metadata_file,
            style='simple_groups',
            title='Erityiskutsut suunnassa ' + direction,
            identifier='special-calls-bulk-bytebufferview-{}-{}'.format(fr.lower(), to.lower()),
            select_predicate=(
                lambda x: (x['direction'] == direction and
                           x['dynamic_variation'] == 1 and
                           'Bulk' in x['id'])),
            group='id',
            measure='response_time',
            variable='dynamic_size',
            revision=revision, checksum=checksum, output=output_type)

    plot(
        custom_benchmarks, gnuplotcommands, plotpath, metadata_file,
        style='histogram',
        title='Erityiskutsujen vertailu eri kutsusuunnissa',
        identifier='special-calls-non-dynamic',
        select_predicate=(
            lambda x: (
                x['dynamic_variation'] == 0 and
                'Field' in x['id'])),
        group='direction',
        measure='response_time',
        variable='id',
        revision=revision, checksum=checksum, output=output_type)


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

    kwargs = {}
    if FNULL is not None:
        kwargs['stdout'] = FNULL
        kwargs['stderr'] = FNULL

    try:
        success = call(['adb', 'pull',
                        dev_path + '/' + filename,
                        tmp_path], **kwargs)
    except OSError:
        success = -1
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

def render_perf_reports_for_measurement(identifier, measurements, measurement_path, output_path, output_command=False):
    path = identifier.split("/")
    if len(path) < 2:
        print 'Invalid identifier {}'.format(identifier)
        exit(1)
    if len(path) == 3:
        revision, class_, dynamic_size = path
    elif len(path) == 2:
        revision, class_ = path
        dynamic_size = None

    def match_measurement(measurement):
        m = measurement[0]
        return (m.get('code-revision') == revision and
                m.get('tool') == 'LinuxPerfRecordTool')

    def match_measurement_run(m):
        if m.get('class').lower() != class_.lower():
            return False
        if dynamic_size and m.get('dynamic_size') != int(dynamic_size):
            return False
        if 'Filename' not in m or m['Filename'] is None:
            return False
        return True

    datafiles = []
    for measurement in filter(match_measurement, measurements): #TODO: multiple?
        mid = measurement[0].get('id')
        zpath = os.path.join(measurement_path, 'perfdata-{}.zip'.format(mid))
        try:
            measurement_zipfile = zipfile.ZipFile(zpath, 'r')
            datafiles.append({
                'zip': measurement_zipfile,
                'zip_path': zpath,
                'mid': mid,
                'csv': measurement_zipfile.open('{0}/benchmarks-{0}.csv'.format(mid))
            })
        except zipfile.BadZipfile:
            print 'Bad zip file %s' % zpath
        except IOError as e:
            print 'Problem with zip file %s' % zpath
            print e

    benchmarks = []
    for df in datafiles:
        benchmarks.append({
            'zip': df['zip'],
            'mid': df['mid'],
            'metadata': read_datafiles([df['csv']], silent=output_command)
        })

    matching_benchmarks = []
    for bm in benchmarks:
        for row in bm['metadata']:
            if match_measurement_run(row):
                matching_benchmarks.append({
                    'zip': bm['zip'],
                    'mid': bm['mid'],
                    'filename': row['Filename']
                })

    for record in matching_benchmarks:
        perf_file = record['zip'].extract('{}/{}'.format(record['mid'], record['filename']), '/tmp')
        try:
            command_parts = [
                #"/home/tituomin/droid/src/out/host/linux-x86/bin/perfhost report",
                #"/home/tituomin/install/linux-4.2.0/tools/perf/perf report",
                "perf report",
                "-i {}",
                "--header",
                "--symfs=/home/tituomin/droid-symbols",
                "--kallsyms=/home/tituomin/droid/linux-kernel/kallsyms"
            ]
            #if not output_command:
            command_parts.extend([
                "-g graph,0,caller",
                #"--parent='dvmPlatformInvoke'",
                #"-s parent",
                "--stdio",
                "| c++filt",
                ">/tmp/out.txt"
            ])
            command = " ".join(command_parts).format(perf_file)
            if output_command:
                print command
                exit(0)
            else:
                call([command], shell=True)
        except OSError as e:
            print e.filename, e.message, e.args

    for f in datafiles:
        f['zip'].close()
    print "Profile for identifier", identifier
    with open('/tmp/out.txt', 'r') as f:
        print f.read()
    exit(0)

if __name__ == '__main__':
    if len(argv) < 4 or len(argv) > 6:
        print argv[0]
        print "\n    Usage: %s input_path output_path limit [pdfviewer] [separate]\n".format(argv[0])
        exit(1)

    FNULL = open(os.devnull, 'w')

    method = argv[0]
    measurement_path = os.path.normpath(argv[1])
    output_path = argv[2]

    if 'plotlatex' in method:
        latex = 'plotlatex'
        method = 'curves'
    elif 'plotsvg' in method:
        latex = 'plotsvg'
        method = 'curves'
    else:
        latex = None

    output_command = False
    if len(argv) > 5:
        if argv[5] == 'show-command':
            output_command = True

    limit = argv[3]
    if len(argv) > 4:
        pdfviewer = argv[4]
    else:
        pdfviewer = None

    if len(argv) == 6:
        group = (not argv[5] == "separate")
    else:
        group = True

    if output_command:
        system_stdout = sys.stdout
        system_stderr = sys.stderr
        sys.stdout = FNULL
        sys.stderr = FNULL

    sync_measurements(DEVICE_PATH, measurement_path, MEASUREMENT_FILE)

    f = open(os.path.join(measurement_path, MEASUREMENT_FILE))

    try:
        measurements = read_measurement_metadata(f, group)
    finally:
        f.close()

    limited_measurements = filter(lambda x: int(x[0].get('repetitions', 0)) >= int(limit),
                                  measurements.values())

    # ID = revision/checksum/class[/dynamic_size]
    if 'perf_select' in method:
        identifier = argv[4]
        if output_command:
            sys.stdout = system_stdout
            sys.stderr = system_stderr
            FNULL.close()
        render_perf_reports_for_measurement(identifier, limited_measurements, measurement_path, output_path, output_command=output_command)
        exit(0)

    csv_files = set()
    for f in glob.iglob(measurement_path + '/benchmarks-*.csv'):
        try:
            csv_files.add(f.split('.csv')[0].split('benchmarks-')[1])
        except IndexError:
            pass

    if len(limited_measurements) > 20:
        i = len(limited_measurements) - 20 + 1
        splice = limited_measurements[-20:]
    else:
        i = 1
        splice = limited_measurements

    print "\nAvailable compatible measurements. Choose one"
    for m in splice:
        b = m[0]
        warning = ""
        if int(b.get('rounds')) == 0:
            warning = " <---- WARNING INCOMPLETE MEASUREMENT"
        print """
    [{idx}]:     total measurements: {num}
                           local: {local}
                     repetitions: {reps}
                     description: {desc}
                          rounds: {rounds}{warning}
                              id: {mid}
                        checksum: {ck}
                        revision: {rev}
                            tool: {tool}
                             cpu: {freq} KHz
                             set: {bset}
                          filter: {sfilter}
                           dates: {first} -
                                  {last}
    """.format(
            local=b.get('id') in csv_files,
            num=len(m),
            mid=b.get('id'),
            idx=i,
            warning=warning,
            last=m[-1]['end'],
            rounds=reduce(lambda x, y: y + x, [int(b['rounds']) for b in m]),
            reps=b.get('repetitions'),
            ck=b.get('code-checksum'),
            rev=b.get('code-revision'),
            tool=b.get('tool'),
            freq=b.get('cpu-freq'),
            bset=b.get('benchmark-set'),
            desc=b.get('description'),
            sfilter=b.get('substring-filter'),
            first=b.get('start')
        )

        i += 1

    try:
        response = raw_input("Choose set 1-{last} >> ".format(last=i - 1))
    except EOFError:
        print 'Exiting.'
        exit(1)

    benchmark_group = limited_measurements[int(response) - 1]

    filenames = []
    ids = []
    multiplier = 0
    for measurement in benchmark_group:
        if 'LinuxPerfRecordTool' in measurement['tool']:
            basename = "perfdata-{n}.zip"
        else:
            basename = "benchmarks-{n}.csv"
        filenames.append(
            basename.format(n=measurement['id']))
        if 'logfile' in measurement:
            filenames.append(measurement['logfile'])
        ids.append(measurement['id'])
        multiplier += int(measurement['rounds'])

    files = []
    for filename in filenames:
        sync_measurements(DEVICE_PATH, measurement_path,
                          filename, update=False)
        if filename not in [m.get('logfile') for m in benchmark_group]:
            files.append(open(os.path.join(measurement_path, filename)))

    first_measurement = benchmark_group[0]

    global_values = {
        'repetitions': first_measurement['repetitions'],
        'is_allocating': first_measurement['benchmark-set'] == 'ALLOC',
        'multiplier': multiplier
    }

    perf = False
    if 'LinuxPerfRecordTool' in first_measurement['tool']:
        print 'Perf data downloaded.'
        perf = True
    if not perf:
        try:
            benchmarks = read_datafiles(files)

        finally:
            for f in files:
                f.close()

        benchmark_group_id = os.getenv('PLOT_ID', str(uuid.uuid4()))
        plot_prefix = 'plot-{0}'.format(benchmark_group_id)

        if latex is not None:
            output_filename = os.path.join(output_path, plot_prefix)
        else:
            output_filename = os.path.join(output_path, plot_prefix + '.pdf')
        plot_filename = plot_prefix + '.gp'

        plotfile = open(os.path.join(output_path, plot_filename), 'w')
        metadata_file = open(os.path.join(
            output_path, plot_prefix + '-metadata.txt'), 'w')

        measurement_ids = " ".join(ids)
        metadata_file.write("-*- mode: perf-report; -*-\n\n")
        metadata_file.write("id: {0}\n".format(benchmark_group_id))
        metadata_file.write("measurements: {0}\n".format(measurement_ids))

        benchmarks = preprocess_benchmarks(benchmarks, global_values, latex=latex)

        animate = False
        if pdfviewer == 'anim':
            plot_type = 'animate'
            pdfviewer = None
        elif pdfviewer == 'gradient':
            plot_type = 'gradient'
            pdfviewer = None
        else:
            plot_type = None

    if 'curves' in method:
        function = plot_benchmarks
    elif 'distributions' in method:
        function = plot_distributions
    if perf or not function:
        exit(0)

    function(
        benchmarks,
        output_filename,
        PLOTPATH,
        plotfile,
        benchmark_group_id,
        metadata_file,
        plot_type=plot_type,
        revision=first_measurement['code-revision'],
        checksum=first_measurement['code-checksum'],
        latex=latex)

    plotfile.flush()
    plotfile.close()
    if plot_type == 'animate':
        print "Press enter to start animation."
    call(["gnuplot", plotfile.name])
    if pdfviewer:
        call([pdfviewer, str(output_filename)])
    print "Final plot",
    if 'animate' != plot_type:
        print str(output_filename)
    else:
        print str(plot_filename)
    print(benchmark_group_id)
    exit(0)
