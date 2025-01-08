import os
from pygnuplot import gnuplot

g = gnuplot.Gnuplot()

# Set plotting style
g.set(
    terminal="kittycairo transparent",
    xdata="time",
    timefmt='"%Y-%m-%d %H:%M:%S"',
    xrange='["2013-01-15 00:00:00":"2013-02-15 23:59:59"]',
    yrange="[*:*]",
    datafile='separator ","',
    palette="defined (-1 'red', 1 'green')",
    cbrange="[-1:1]",
    style="fill solid noborder",
    boxwidth="60000 absolute",
    title='"AUDJPY" textcolor rgbcolor "white"',
)
g.unset("colorbox")
os.system("clear")
g.plot(
    "'basic.csv' using (strptime('%Y-%m-%d', strcol(1))):2:4:3:5:($5 < $2 ? -1 : 1) with candlesticks palette"
)
_ = input()
os.system("clear")
