Xnuplot
=======

Xnuplot_ ("ex-new-plot") is a Python package for driving the interactive
plotting program Gnuplot_. It uses Noah Spurrier's Pexpect_ module to
communicate with Gnuplot (hence the name *Xnuplot*), and can efficiently pipe
text as well as binary data, including data contained in NumPy_ arrays, to
Gnuplot.

.. _Xnuplot: https://github.com/marktsuchida/Xnuplot
.. _Gnuplot: http://www.gnuplot.info/
.. _Pexpect: http://www.noah.org/wiki/pexpect
.. _NumPy: http://numpy.scipy.org/

Currently, Xnuplot only works on UNIX platforms, where Pexpect runs. I expect
that it will be possible to port Xnuplot to Windows using the WinPexpect_
module, though I don't know when I'll have a chance to try this. Alternatively,
you might want to try the Gnuplot.py_ module, which is cross-platform.

.. _WinPexpect: https://bitbucket.org/geertj/winpexpect/wiki/Home
.. _Gnuplot.py: http://gnuplot-py.sourceforge.net/

This documentation for Xnuplot is not yet complete, so you will need to look at
the code for some advanced features. Parts of the code (the
:mod:`xnuplot.utils` and :mod:`xnuplot.numutils` modules) are experimental, so
expect changes to the API.

Xnuplot has so far only been tested in a very specific environment (Mac OS X
and Gnuplot 4.4.0). Bug reports and other feedback would be greatly
appreciated.


Quick introduction
------------------

Xnuplot does not attempt to construct a full abstraction of Gnuplot commands;
rather it aims to provide transparent access to as much as possible of
Gnuplot's functionality, while taking care of the logistics of passing binary
and ascii data from Python to Gnuplot. No attempt is made at providing Python
methods for things that can be done by issuing a simple Gnuplot command.

You will therefore need to be familiar with at least the basics of using
Gnuplot as a standalone application. Gnuplot has an excellent manual__.

__ http://www.gnuplot.info/documentation.html

To follow the examples below, you will need to be familiar with the Gnuplot
keywords ``plot``, ``with``, ``using``, ``set``, and ``xrange``, among others.

Here's a basic example of plotting functions and data.

::

  >>> import xnuplot
  >>> plot = xnuplot.Plot() # A container object that retains the source data.
  >>> plot.append("sin(x)") # Plot a function.
  >>> plot("set xrange [0.0:2.0]") # Send any Gnuplot command. Replotting is automatic by default.
  ''
  >>> plot.append(("0.0 0.0\n0.5 1.0\n1.0 0.5", "notitle with linespoints")) # Plot data.
  >>> plot # Plot objects are a subclass of list.
  <Plot ['sin(x)', <PlotData source=str options='notitle with linespoints' mode=pipe>]>
  >>> plot[0] = "cos(x)" # So you can replace plot items (functions or data).
  >>> plot.interact() # Enter the Gnuplot command line.
  escape character is `^]'

  gnuplot> show yrange

          set yrange [ * : * ] noreverse nowriteback  # (currently [-0.600000:1.00000] )

  gnuplot> set style function linespoints
  gnuplot> # Typing CTRL-] exits interactive mode.
  >>> plot.pop(0) # Use any list method to edit the plot.
  'cos(x)'
  >>> plot
  <Plot [<PlotData source=str options='notitle with linespoints' mode=pipe>]>
  >>> plot.close()

If NumPy is installed on your system, the functions :func:`~xnuplot.array`,
:func:`~xnuplot.record`, and :func:`~xnuplot.matrix` become available.
These are used to generate appropriate Gnuplot binary data descriptors, and
they correspond to Gnuplot's ``binary array``, ``binary record``, and ``binary
matrix`` keywords, respectively.

.. note::

   The keywords used to convey to Gnuplot the format of binary data (especially
   the ``array`` and ``record`` keywords) can be a bit confusing at first. I
   intend to write a general introduction to this topic at some point.

When plot items are created by wrapping NumPy arrays with one of these
functions, the array is sent to Gnuplot as binary data. In most cases, Xnuplot
automatically takes care of generating the right keywords to tell Gnuplot the
size and data type of your array::

  import xnuplot
  import numpy
  x = numpy.linspace(0, 5.0 * numpy.pi, 200)
  y1 = numpy.sin(x)
  y2 = numpy.cos(x)
  data = numpy.column_stack((x, y1, y2)) # Make a 200-by-3 array.
  plot = xnuplot.Plot()
  plot.append(xnuplot.record(data, using=(0, 1), options="notitle with lines"))
  plot.append(xnuplot.record(data, using=(0, 2), options="notitle with lines"))

One very handy feature of Xnuplot is the ability to save plots, together with
the plotted data. You can load the saved plot later and make changes::

  plot.save("sincos.xnuplot")
  plot.close()
  del plot, data
  plot = xnuplot.load("sincos.xnuplot")
  plot("unset key")
  plot("set title 'sin(x) and cos(x)')

You can also clone plots, allowing you to use one plot as a template for
another::

  p1 = xnuplot.Plot()
  p1.append("sin(x)")
  p1("set xlabel 'x'")
  p1("set ylabel 'y'")
  p1("set title 'y = sin(x)'")
  p2 = p1.clone() # Make a second plot with the same title, labels, and content.
  p2[0] = "cos(x)"
  p2("set title 'y = cos(x)'")

Xnuplot also makes it easy to use Gnuplot's multiplot functionality. A
multiplot in Xnuplot behaves as a list containing subplots, each of which are
active :class:`~xnuplot.Plot` instances::

  mp = xnuplot.GridMultiplot(1, 2) # One row and two columns.
  mp.extend([p1, p2])
  mp.title = "Trigonometric functions"

Finally, Xnuplot comes with a simple command line script, :program:`xnuplot`,
to display saved plots. In addition to providing a quick way to view saved
plots, it allows you to edit the plot settings (though not the data) from the
Gnuplot command line, and is handy for minor tweaks like modifying the plot
title and labels. It can also be used to quickly generate image or
postscript/PDF output. Type ``xnuplot --help`` to get a list of command line
options.


Prerequisites
-------------

- Python 2.6 or 2.7 (not Python 3)
- Gnuplot 4.4 or above
- Pexpect (tested with version 2.3)
- A UNIX operating system on which Pexpect works properly (Xnuplot is currently
  developed and tested on Mac OS X)


Documentation
-------------

.. toctree::
   :maxdepth: 1

   xnuplot
   numplot
   gnuplot
   utils
   numutils


Indexes and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

