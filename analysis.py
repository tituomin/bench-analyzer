#!/usr/bin/python

from numpy import polyfit, reshape, polyval

def linear_fit_columns(x, y):
    p, residuals, rank, singular_values, rcond = polyfit(x, y, 1, full=True)
    ynorm = normalized(x, y, p)
    pnorm, residuals, rank, singular_values, rcond = polyfit(x, ynorm, 1, full=True)
    return p, residuals

def normalized(x, y, poly):
    # normali
    return (x - poly[1]) / poly[0]

def linear_fit(rows):
    columns = reshape(rows, len(rows)*len(rows[0]), order='F').reshape((len(rows[0]), -1))
    x = columns[0]
    columns = columns[1:]
    residuals = [linear_fit_columns(x, col)[1][0] for col in columns]
    polys = [linear_fit_columns(x, col)[0] for col in columns]
    return x, polys, residuals

def estimate_measuring_overhead(rows):
    x, polys, residuals = linear_fit(rows)
    print polys
    return [p[1] for p in polys]
