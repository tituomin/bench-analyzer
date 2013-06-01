#!/usr/bin/python

import os
import uuid

init_plots_pdf = """
set terminal pdfcairo size 32cm,18cm
set output '{filename}'
"""

init_plots_gp = """
set key outside
set size 1, 0.95
set xlabel "Number of parameters"
set ylabel "Response time (ms)"
set label 1 "{bid}" at graph 0.01, graph 1.1
"""

templates = {}

templates['binned'] = """
set title '{title}
set label 2 "page {page}" at graph 0.01, graph 1.06
binwidth={binwidth}
set boxwidth binwidth
set style fill solid 1.0
# border lt -1
bin(x,width)=width*floor(x/width) + width/2.0
plot '{filename}' using (bin($1,binwidth)):(1.0) notitle smooth freq with boxes lt rgb "dark-olivegreen"
"""

templates['binned_init'] = """
set title '{title}
binwidth={binwidth}
set boxwidth binwidth
set style fill solid 1.0
#clear
#unset multiplot
#set multiplot
#set size 1, 0.95
#set origin 0, 0
set xrange [{min_x}:{max_x}]
set yrange [0:1000*0.66]
"""
# border lt -1
#bin(x,width)=width*floor(x/width) + width/2.0

templates['binned_frame'] = "plot '-' using 1:2 notitle with boxes lt rgb \"dark-olivegreen\"\n{values}\ne\n"

templates['simple_groups'] = """
set title '{title}'
set label 2 "page {page}" at graph 0.01, graph 1.06
set xlabel "{xlabel}"
plot for [I=2:{last_column}] '{filename}' index {index} using 1:I title columnhead with linespoints
"""

templates['fitted_lines'] = """
set title '{title}'
set label 2 "page {page}" at graph 0.01, graph 1.06
set xlabel "{xlabel}"
plot for [I=2:{last_real_column}] '{filename}' index {index} using 1:I title columnhead with points, \
for [I={first_fitted_column}:{last_column}] '{filename}' index {index} using 1:I title columnhead with lines
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
plot [] [{miny}:*] for [I=2:{last_column}] '{filename}' index {index} using I:xtic(1) title columnhead with histogram
"""

def init(plotscript, filename, measurement_id, output='pdf'):
    if output == 'pdf':
        plotscript.write(init_plots_pdf.format(filename=filename))
    plotscript.write(init_plots_gp.format(bid=measurement_id))


def output_plot(data_headers, data_rows, plotpath, plotscript, title, specs, style, page, xlabel, additional_data=None):

    template = templates[style]

    if plotpath:
        # external data
        filename = os.path.join(plotpath, "plot-" + str(uuid.uuid4()) + ".data")
        plotdata = open(filename, 'w')
        plotdata.write(print_benchmarks(data_headers, data_rows, title, **specs))

    miny = 0
    for row in data_rows:
        for cell in row[1:]:
            if cell < miny:
                miny = cell
    if miny == None:
        miny = '*'

    if style == 'binned':
        plotscript.write(template.format(
           title = title, page = page, filename = filename, index = 0, last_column = len(data_rows[0]),
           xlabel = xlabel, miny=miny, **additional_data))

    elif style == 'fitted_lines':
        length = len(data_headers) - 1
        last_real_column = 1 + length / 2
        first_fitted_column = last_real_column + 1
        plotscript.write(template.format(
           title = title, page = page, filename = filename, index = 0, last_column = len(data_rows[0]),
           xlabel = xlabel, miny=miny, last_real_column=last_real_column, first_fitted_column=first_fitted_column))

    else:
        plotscript.write(template.format(
           title = title, page = page, filename = filename, index = 0, last_column = len(data_rows[0]),
           xlabel = xlabel, miny=miny))

    

def print_benchmarks(data_headers, data_rows, title, group=None, variable=None, measure=None):
    result = '#{0}\n'.format(title)
    if group and variable and measure:
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
