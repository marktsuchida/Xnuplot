Xnuplot
=======

**Xnuplot** ("ex-new-plot") is a Python package for driving the interactive
plotting program Gnuplot_. It uses Noah Spurrier's Pexpect_ module to
communicate with Gnuplot (hence the name *Xnuplot*), and can efficiently pipe
text as well as binary data, including data contained in NumPy_ arrays, to
Gnuplot.

.. _Gnuplot: http://www.gnuplot.info/
.. _Pexpect: http://www.noah.org/wiki/pexpect
.. _NumPy: http://numpy.scipy.org/

Xnuplot does not attempt to construct a full abstraction of Gnuplot commands;
rather it aims to provide transparent access to as much as possible of
Gnuplot's functionality, while taking care of the logistics of passing binary
and ascii data from Python to Gnuplot. No attempt is made at providing Python
methods for things that can be done by issuing a simple Gnuplot command.

You will therefore need to be familiar with at least the basics of using
Gnuplot as a standalone application. Gnuplot has an excellent manual__.

__ http://www.gnuplot.info/documentation.html

Currently, Xnuplot only runs on UNIX-based systems (because of the requirement
for Pexpect).

Please see here_ for further documentation. License information is contained in
the LICENSE file.

.. _here: http://marktsuchida.github.com/Xnuplot/

