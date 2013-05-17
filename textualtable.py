#/usr/bin/python

def make_textual_table(headers, rows):
    result = ""
    max_widths = []

    for x in headers:
        max_widths.append(len(str(x)))

    for row in rows:
        for i, x in enumerate(row):
            l = len(str(x))
            if max_widths[i] < l:
                max_widths[i] = l
                        
    row_format = ["{{:>{w}}}   ".format(w=w) for w in max_widths]
    row_format = "".join(row_format) + "\n"

    result += row_format.format(*headers)
    for row in rows:
        result += row_format.format(*row)
    return result
