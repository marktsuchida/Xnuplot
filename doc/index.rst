Xnuplot
=======

**Xnuplot** ("ex-new-plot") is a Python package for driving the interactive
plotting program Gnuplot_. It uses Noah Spurrier's Pexpect_ module for
communication with Gnuplot (hence the name *Xnuplot*), and can efficiently pipe
text as well as binary data, including data contained in NumPy_ arrays, to
Gnuplot.

.. _Gnuplot: http://www.gnuplot.info/
.. _Pexpect: http://www.noah.org/wiki/pexpect
.. _NumPy: http://numpy.scipy.org/

Currently, Xnuplot only works on UNIX platforms, where Pexpect runs. I expect
that it will be possible to port Xnuplot to Windows using the WinPexpect_
module, though I don't know when I'll have a chance to try this. Alternatively,
you might want to try the Gnuplot.py_ module, which is cross-platform).

.. _WinPexpect: https://bitbucket.org/geertj/winpexpect/wiki/Home
.. _Gnuplot.py: http://gnuplot-py.sourceforge.net/

This documentation for Xnuplot is not yet complete, so you will need to look at
the code for some advanced features. Parts of the code (the
:mod:`xnuplot.utils` and :mod:`xnuplot.numutils` modules) are experimental, so
expect changes to the API.

Xnuplot has so far only been tested in a very specific environment (Mac OS X
and Gnuplot 4.4.0). Bug reports and other feedback would be highly appreciated.


Quick introduction
------------------

Xnuplot does not attempt to construct a full abstraction of Gnuplot commands;
rather it aims to provide transparent access to as much as possible of
Gnuplot's functionality, while taking care of the logistics of passing binary
and ascii data to Gnuplot. No attempt is made to provide Python methods for
things that can be done by issuing a simple Gnuplot command.

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

The :mod:`xnuplot.numplot` module makes it easy to plot data from NumPy arrays.
Instances of :class:`xnuplot.numplot.Plot` are similar to those of
:class:`xnuplot.Plot`, except that they provide convenience methods for
handling NumPy arrays.

You will need a basic understanding of how indexing of binary data works in
Gnuplot (some day I'll write a tutorial on this, because I found it quite
confusing until I got it). Note that the data is piped to Gnuplot in its binary
form, without the overhead of converting it into ascii.

::

  import numpy
  from xnuplot import numplot
  x = numpy.linspace(0, 5.0 * numpy.pi, 200)
  y1 = numpy.sin(x)
  y2 = numpy.cos(x)
  data = numpy.column_stack((x, y1, y2)) # Make a 200-by-3 array.
  plot = numplot.Plot()
  plot.append_record(data, options="notitle with lines", using=(0, 1))
  plot.append_record(data, options="notitle with lines", using=(0, 2))

Just to showcase some high-level features, here is an example of plotting an
image. There is even experimental support for getting mouse input::

  >>> import numpy
  >>> from xnuplot import numplot, utils, numutils
  >>> t = numpy.linspace(0, 10.0 * numpy.pi, 512)
  >>> x = numpy.sin(t)
  >>> y = numpy.cos(t)
  >>> z = numpy.outer(x, y)
  >>> z.shape
  (512, 512)
  >>> numutils.imshow(plot, z) # Append the image to the plot and adjusts axes.
  >>> plot
  <Plot [<PlotData source=ndarray options="binary array=(512,512) format='%float64' notitle with image" mode=pipe>]>
  >>> plot("set palette gray")
  >>> vertices = utils.input_polyline(plot, close_polygon=True) # Click to draw and hit Enter to exit.
  >>> vertices
  [(212.55489443378099, 389.12291950886799),
   (130.79213051823399, 235.31336971350601),
   (311.81017274472202, 137.383765347885),
   (422.46506717850298, 298.87680763983599),
   (344.63320537428001, 429.775579809004)]
  >>> plot.pop() # Hide the polygon that the user drew.
  ('2.125549e+02 3.891229e+02\n1.307921e+02 2.353134e+02\n3.118102e+02 1.373838e+02\n4.224651e+02 2.988768e+02\n3.446332e+02 4.297756e+02\n2.125549e+02 3.891229e+02',
   'axes x1y1 notitle with lines')

Last but not least, there is a simple command line script, :program:`xnuplot`,
to display saved plots. It allows you to edit the plot settings (though not the
data) from the Gnuplot command line, and is handy for minor tweaks like
modifying the plot title as well as for plotting to an image or postscript
file. Type ``xnuplot --help`` to get a list of command line options.


Prerequisites
-------------

- Python 2.6 or 2.7 (not Python 3+)
- Gnuplot 4.4 or above
- Pexpect (tested with version 2.3)
- A UNIX operating system on which Pexpected works properly (Xnuplot is
  currently developed and tested on Mac OS X)


Documentation
-------------

Start with the ``xnuplot`` package and ``xnuplot.numplot`` module for the
basics.

.. toctree::
   :maxdepth: 2

   xnuplot


Indexes and tables
------------------

* :ref:`genindex`
* :ref:`modindex`
* :ref:`search`

