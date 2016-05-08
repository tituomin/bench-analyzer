#!/usr/bin/python
import sys
import re
import codecs

RE = {
    'indentation': '[ ]{10}',
    'comment': '^#',
    'dashes': '--+',
    'pipes': '^([ |]+)',
    'percentage': '(\D+)(\d+\.\d+)%',
    'symbol': '^([^%]+%)* ([^%]+)$'
}

VSPACE = r"(*@\vspace{-0.15cm}@*)"

RE['pipes_only'] = RE['pipes'] + '$'
for k, v in RE.iteritems():
    RE[k] = re.compile(v)

def format_to_latex(filename):
    f = codecs.open(filename, 'r', 'utf8')
    print r"""
\lstset{
  basicstyle=\linespread{0}\rmfamily\tiny,
  escapeinside={(*@}{@*)},
  columns=fixed,
  basewidth=0.5em,
  mathescape,
  breaklines=false,breakatwhitespace=false,
  moredelim=[is][\underbar]{<<@<<}{>>@>>}
}
\begin{lstlisting}
"""
    def p(line):
        print line.rstrip().encode('utf8')
        print VSPACE

    for line in f:
        line = RE['dashes'].sub('', line)
        line = RE['indentation'].sub('       ', line)
        if RE['comment'].match(line):
            continue
        if RE['pipes_only'].match(line):
            p(line)
            p(line)
            continue

        pipe_part = None
        m = RE['pipes'].match(line)
        if m: pipe_part = m.group(1)
        else: pipe_part = None

        percentage = ""
        m = RE['percentage'].search(line)
        if m:
            percentage_value = m.group(2)
            if len(percentage_value) < 5:
                phantom = '00'
            else:
                phantom = '0'
            percentage = '$\\underline{{\\phantom{{{}}}{}\\%}}$'.format(phantom,percentage_value)

        symbol = "\n"
        m = RE['symbol'].match(line)
        if m: symbol = m.group(2).strip()

        #$ \underline{\phantom{ab}46.21\%  dvmDecodeIndirectRef(Thread*, \_jobject*)} $
        pipe_part_f = pipe_part
        if pipe_part_f == None:
            pipe_part_f = ''
        if len(pipe_part_f.strip()) == 0:
            pipe_part_f = pipe_part_f[:-1] + '|'
         
        print "{}{} {}".format(pipe_part_f,percentage, symbol)
        if pipe_part == None or len(pipe_part.strip()) == 0:
            print
            continue
        print VSPACE

    print """
\end{lstlisting}
"""

    f.close()

if __name__ == '__main__':
    filename = sys.argv[1]
    format_to_latex(filename)
