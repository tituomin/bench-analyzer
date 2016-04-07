#!/usr/bin/python
# -*- coding: utf-8 -*-

import os
import uuid

INIT_PALETTE = """
# line styles for ColorBrewer Dark2
# for use with qualitative/categorical data
# provides 8 dark colors based on Set2
# compatible with gnuplot >=4.2
# author: Anna Schneider

# line styles
set style line 1 pt 7 lt 1 lc rgb '#1B9E77' # dark teal
set style line 2 pt 7 lt 1 lc rgb '#D95F02' # dark orange
set style line 3 pt 7 lt 1 lc rgb '#7570B3' # dark lilac
set style line 4 pt 7 lt 1 lc rgb '#E7298A' # dark magenta
set style line 5 pt 7 lt 1 lc rgb '#66A61E' # dark lime green
set style line 6 pt 7 lt 1 lc rgb '#E6AB02' # dark banana
set style line 7 pt 7 lt 1 lc rgb '#A6761D' # dark tan
set style line 8 pt 7 lt 1 lc rgb '#666666' # dark gray

# palette
set palette maxcolors 8
set palette defined ( 0 '#1B9E77',\
    	    	      1 '#D95F02',\
		      2 '#7570B3',\
		      3 '#E7298A',\
		      4 '#66A61E',\
		      5 '#E6AB02',\
		      6 '#A6761D',\
		      7 '#666666' )
"""

INIT_PLOTS_PDF = """
set terminal pdfcairo size 32cm,18cm
set size 1, 0.95
set output '{filename}'
"""

INIT_PLOTS_LATEX = """
set terminal epslatex color
set pointsize 1.0
set format y "$%.0s%cs$"
"""

INIT_PLOTS_COMMON = """
set grid
set xlabel "kutsuparametrien määrä"
set ylabel "vasteaika"
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

SET_TITLE_AND_PAGE_LABEL = """
set title '{title}'
set label 2 "page {page}" at screen 0.9, screen 0.95
"""

TEMPLATES['simple_groups'] = """
set xlabel "{xlabel}"
set key inside top left Left box title "{grouptitle}"
plot for [I=2:{last_column}] '{filename}' index {index} using 1:I title columnhead with points ls I
"""

TEMPLATES['fitted_lines'] = """
set xlabel "{xlabel}"
plot for [I=2:{last_real_column}] '{filename}' index {index} using 1:I title columnhead with points, \
for [I={first_fitted_column}:{last_column}] '{filename}' index {index} using 1:I title columnhead with lines
"""

TEMPLATES['named_columns'] = """
set yrange [-500:*]
set xlabel "{xlabel}"
plot for [I=2:{last_column}] '{filename}' index {index} using I:xtic(1) title columnhead with linespoints
"""

TEMPLATES['histogram'] = """
set xlabel "{xlabel}"
unset x2tics
set xtics rotate
#set boxwidth 20
#set style fill solid border lc rgbcolor "black"
set style data histograms
set style histogram clustered
set style fill solid 1.0 border lt -1
plot [] [{miny}:*] for [I=2:{last_column}] '{filename}' index {index} using I:xtic(1) title columnhead with histogram
"""

measurement_id = None
plot_directory = '/home/tituomin/gradu/paper/figures/plots'

def init(plotscript, filename, mid, output_type='pdf'):
    global measurement_id, plot_directory
    measurement_id = mid
    if output_type == 'pdf':
        plotscript.write(INIT_PLOTS_PDF.format(filename=filename))
        plotscript.write(INIT_PLOT_LABEL_PDF.format(bid=measurement_id))
    elif output_type == 'latex':
        plotscript.write(INIT_PLOTS_LATEX)
    plotscript.write(INIT_PLOTS_COMMON)
    plotscript.write(INIT_PALETTE)

GROUPTITLES={
    'direction': 'kutsusuunta',
    'from': 'kieli'
}

def output_plot(data_headers, data_rows, plotpath,
                plotscript, title, specs, style, page,
                xlabel, additional_data=None, output='pdf'):
    global plot_directory
    template = TEMPLATES[style]

    if output == 'latex':
        plotscript.write("set output '{}'".format(
            os.path.join(plot_directory,
                         "plot-{}-page-{:02d}.tex".format(measurement_id,
                                                          page))))

    if plotpath:
        # external data
        filename = os.path.join(plotpath, "plot-" + str(uuid.uuid4()) + ".data")
        plotdata = open(filename, 'w')
        specs['convert_to_seconds'] = False # (output == 'latex')
        plotdata.write(print_benchmarks(data_headers, data_rows, title, **specs))

    miny = 0
    for row in data_rows:
        for cell in row[1:]:
            if cell < miny:
                miny = cell
    if miny == None:
        miny = '*'

    if output == 'pdf':
        plotscript.write(SET_TITLE_AND_PAGE_LABEL.format(page=page,title=title))

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
        grouptitle = GROUPTITLES.get(specs['group'], 'group')
        plotscript.write(template.format(
            title = title, page = page, filename = filename, index = 0, last_column = len(data_rows[0]),
            xlabel = xlabel, miny=miny, grouptitle=grouptitle))


    

def print_benchmarks(data_headers, data_rows, title, group=None, variable=None, measure=None, convert_to_seconds=False):
    result = '#{0}\n'.format(title)
    print(measure)
    if group and variable and measure:
        result = '#measure:{m} variable:{v} group:{g}'.format(
            m=measure, v=variable, g=group)

    result = " ".join([format_value(k) for k in data_headers])
    result += '\n'

    for row in data_rows:
        results = []
        for i, v in enumerate(row):
            convert = convert_to_seconds and i > 0
            results.append(format_value(v, convert_to_seconds=convert))
        result += ' '.join(results) + '\n'
    result += '\n\n'

    return result

def format_value(value, convert_to_seconds=False):
    if value == None:
        return "-500"
    if type(value) == str:
        return '"{0}"'.format(value)
    if type(value) == int:
        # 1000000000 = 1 sekuntti
        strval = str(value)
        if convert_to_seconds == False:
            return strval
        strval = strval.zfill(10)
        strlen = len(strval)
        return "{}.{}".format(
            strval[0:strlen-9],
            strval[strlen-9:])
            
    return str(value)
#1000000000
#     10000
def hex_color_gradient(start, end, point):
    # start, end are tuples with r,g,b values (integer)
    # point is a point between 0 (start) and 1000 (end)

    return "#" + "".join(
        "{:0>2X}".format(
            int(start[i] +
                ((end[i] - start[i]) * (float(point)))))
        for i in range(0,3))

