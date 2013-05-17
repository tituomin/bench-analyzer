#!/usr/bin/python

import os
import uuid

init_plots_gp = """
set terminal pdfcairo size 32cm,18cm
set output '{filename}'
set key outside
set size 1, 0.95
set xlabel "Number of parameters"
set ylabel "Response time (ms)"
set label 1 "{bid}" at graph 0.01, graph 1.1
"""

templates = {}
templates['simple_groups'] = """
set title '{title}'
set label 2 "page {page}" at graph 0.01, graph 1.06
set xlabel "{xlabel}"
plot for [I=2:{last_column}] '{filename}' index {index} using 1:I title columnhead with linespoints
"""

templates['named_columns'] = """
set title '{title}'
set label 2 "page {page}" at graph 0.01, graph 1.06
set xlabel "{xlabel}"
plot for [I=2:{last_column}] '{filename}' index {index} using I:xtic(1) title columnhead with linespoints
"""

templates['histogram'] = """
set title '{title}'
set label 2 "page {page}" at graph 0.01, graph 1.06
set xlabel "{xlabel}"
set xtics rotate
#set boxwidth 20
#set style fill solid border lc rgbcolor "black"
set style data histograms
set style histogram clustered
set style fill solid 1.0 border lt -1
plot for [I=2:{last_column}] '{filename}' index {index} using I:xtic(1) title columnhead with histogram
"""

def init(plotscript, filename, measurement_id):
    plotscript.write(init_plots_gp.format(filename=filename, bid=measurement_id))


def output_plot(data_headers, data_rows, plotpath, plotscript, title, specs, style, page, xlabel):
    template = templates[style]
    filename = os.path.join(plotpath, "plot-" + str(uuid.uuid4()) + ".data")
    plotdata = open(filename, 'w')
    plotdata.write(print_benchmarks(data_headers, data_rows, title, **specs))

    plotscript.write(template.format(
       title = title, page = page, filename = filename, index = 0, last_column = len(data_rows[0]),
       xlabel = xlabel))
    

def print_benchmarks(data_headers, data_rows, title, group=None, variable=None, measure=None):
    result = '#{0}\n'.format(title)
    result = '#measure:{m} variable:{v} group:{g}'.format(
        m=measure, v=variable, g=group)

    result = " ".join([format_value(k) for k in data_headers])
    result += '\n'

    for row in data_rows:
        result += ' '.join([format_value(v) for v in row])
        result += '\n'
    result += '\n\n'

    return result

def format_value(value):
    if value == None:
        return "-500"
    if type(value) == str:
        return '"{0}"'.format(value)
    else:
        return str(value)
