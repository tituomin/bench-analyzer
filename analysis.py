#!/usr/bin/python

from numpy import polyfit

def linear_fit(x, y):
    p, residuals, rank, singular_values, rcond = polyfit(x, y, 1, full=True)
    ynorm = normalized(x, y, p)
    pnorm, residuals, rank, singular_values, rcond = polyfit(x, ynorm, 1, full=True)
    return p, residuals

def normalized(x, y, poly):
    # normali
    return (x - poly[1]) / poly[0]
