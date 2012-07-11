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

Currently, Xnuplot only works on UNIX platforms, where Pexpect runs. I expect
that it will be possible to port Xnuplot to Windows using the WinPexpect_
module, though I don't know when I'll have a chance to try this. Alternatively,
you might want to try the Gnuplot.py_ module, which is cross-platform.

.. _WinPexpect: https://bitbucket.org/geertj/winpexpect/wiki/Home
.. _Gnuplot.py: http://gnuplot-py.sourceforge.net/

This documentation for Xnuplot is not yet complete, so you will need to look at
the code for some advanced features. Parts of the code (the
``xnuplot.utils`` and ``xnuplot.numutils`` modules) are experimental, so
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
  >>> plot.save("test.xnuplot") # Save the plot to a file, with all its data and settings.
  >>> del plot
  >>> plot = xnuplot.load("test.xnuplot") # Open and display the saved plot.
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

If NumPy is installed on your system, the functions ``xnuplot.array()``,
``xnuplot.record()``, and ``xnuplot.matrix()`` become available.
These are used to generate appropriate Gnuplot binary data descriptors, and
they correspond to Gnuplot's ``binary array``, ``binary record``, and ``binary
matrix`` keywords, respectively.

.. note::

   The keywords used to convey to Gnuplot the format of binary data (especially
   the ``array`` and ``record`` keywords) can be a bit confusing at first. I
   intend to write a general introduction to this topic at some point.

When plot items are created by wrapping NumPy arrays with these functions, the
array data is piped to Gnuplot in its binary form, without the overhead of
converting it into ascii. In most cases, Xnuplot automatically takes care of
generating the right keywords to tell Gnuplot the size and data type of your
array.

::

  import numpy
  import xnuplot
  x = numpy.linspace(0, 5.0 * numpy.pi, 200)
  y1 = numpy.sin(x)
  y2 = numpy.cos(x)
  data = numpy.column_stack((x, y1, y2)) # Make a 200-by-3 array.
  plot = xnuplot.Plot()
  plot.append(xnuplot.record(data, using=(0, 1), options="notitle with lines"))
  plot.append(xnuplot.record(data, using=(0, 2), options="notitle with lines"))

.. TODO Introduce clone and multiplot facilities here.

Last but not least, Xnuplot comes with a simple command line script,
``xnuplot``, to display saved plots. It allows you to edit the plot
settings (though not the data) from the Gnuplot command line, and is handy for
minor tweaks like modifying the plot title as well as for plotting to an image
or postscript file. Type ``xnuplot --help`` to get a list of command line
options.


Prerequisites
-------------

- Python 2.6 or 2.7 (not Python 3)
- Gnuplot 4.4 or above
- Pexpect (tested with version 2.3)
- A UNIX operating system on which Pexpected works properly (Xnuplot is
  currently developed and tested on Mac OS X)


License
-------

See the LICENSE file.

