#!/usr/bin/python

import os
import uuid

INIT_PLOTS_PDF = """
set terminal pdfcairo size 32cm,18cm
set output '{filename}'
"""

INIT_PLOTS_LATEX = """
set terminal epslatex color
"""

INIT_PLOTS_COMMON = """
set key outside
set size 1, 0.95
set xlabel "Number of parameters"
set ylabel "Response time"
"""

INIT_PLOT_LABEL_PDF = """
set label 1 "{bid}" at graph 0.01, graph 1.06
"""

TEMPLATES = {}

TEMPLATES['binned_init'] = """
set title '{title}
binwidth={binwidth}
set boxwidth binwidth
set style fill solid 1.0
set xrange [{min_x}:{max_x}]
set yrange [0:{max_y}]
"""
# border lt -1
#bin(x,width)=width*floor(x/width) + width/2.0

TEMPLATES['binned_frame'] = """
#set label 2 "{datapoints}" at graph 0.8, graph 1.06
set bmargin 20
set tmargin 20
set rmargin 20
set lmargin 20
plot '-' using 1:2 notitle with boxes lt rgb "{color}"\n{values}\ne\n
#unset xlabel
#unset ylabel
#unset label 1
#unset title
unset xtics
unset ytics
"""

TEMPLATES['simple_groups'] = """
set title '{title}'
set label 2 "page {page}" at screen 0.9, screen 0.95
set xlabel "{xlabel}"
plot for [I=2:{last_column}] '{filename}' index {index} using 1:I title columnhead with linespoints
"""

TEMPLATES['fitted_lines'] = """
set title '{title}'
set label 2 "page {page}" at screen 0.9, screen 0.95
set xlabel "{xlabel}"
plot for [I=2:{last_real_column}] '{filename}' index {index} using 1:I title columnhead with points, \
for [I={first_fitted_column}:{last_column}] '{filename}' index {index} using 1:I title columnhead with lines
"""

TEMPLATES['named_columns'] = """
set yrange [-500:*]
set title '{title}'
set label 2 "page {page}" at screen 0.9, screen 0.95
set xlabel "{xlabel}"
plot for [I=2:{last_column}] '{filename}' index {index} using I:xtic(1) title columnhead with linespoints
"""

TEMPLATES['histogram'] = """
set title '{title}'
set label 2 "page {page}" at screen 0.9, screen 0.95
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
        plotscript.write(INIT_PLOTS_PDF.format(filename=filename))
        plotscript.write(INIT_PLOT_LABEL_PDF.format(bid=measurement_id))
    elif output == 'latex':
        plotscript.write(INIT_PLOTS_LATEX)
    plotscript.write(INIT_PLOTS_COMMON)

def output_plot(data_headers, data_rows, plotpath, plotscript, title, specs, style, page, xlabel, additional_data=None, latex=False):

    template = TEMPLATES[style]

    if plotpath:
        # external data
        if late
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

    if latex:
        plotscript.write('')

    

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

def hex_color_gradient(start, end, point):
    # start, end are tuples with r,g,b values (integer)
    # point is a point between 0 (start) and 1000 (end)

    return "#" + "".join(
        "{:0>2X}".format(
            int(start[i] +
                ((end[i] - start[i]) * (float(point)))))
        for i in range(0,3))

