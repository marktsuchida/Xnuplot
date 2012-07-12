Core classes and functions
==========================

.. module:: xnuplot

Also in the :mod:`xnuplot` module:

.. toctree::
   :maxdepth: 1

   numplot
   gnuplot


.. class:: Plot([autorefresh=True, persist=False, description=None, kwargs...])

   An interface to a 2D Gnuplot plot that remembers (and allows
   modification of) the current plot items.

   :arg bool autorefresh: whether to automatically replot when plot items are
                          added, removed, or replaced or the plot is otherwise
                          modified

   :arg bool persist: whether the plot window (if any) should stay open after
                      Gnuplot quits (*i.e.* after the ``Plot`` object is
                      deleted)

   :arg str description: an arbitrary description that is saved with the plot

   :arg kwargs: additional keyword arguments to the lower-level
                :class:`Gnuplot` or :class:`RawGnuplot` constructors.

   ``Plot`` inherits from ``list``. You can use the standard sequence methods
   (``insert()``, ``append()``, ``pop()``, and others), the ``del`` statement,
   and the indexing operator (``[]``) to add, remove, and replace plot items
   (analogous to the comma-separated arguments to Gnuplot's ``plot`` command).

   If the :attr:`autorefresh` attribute is set to ``True``, simply changing the
   contents of the ``Plot`` container will automatically update the plot.

   Plot items can be

   - a string (*e.g.* ``"sin(x)"``),

   - an :class:`PlotData` instance, or

   - a tuple, (*data* [, *options* [, *mode*]]), which is used as the arguments
     to construct a ``PlotData`` object, where

     * *data* can either be a string in a format that Gnuplot understands,
       or an object that exposes binary data (also must be in a format handled
       by Gnuplot) through the buffer protocol,

     * *options* is a string containing Gnuplot plot options (*e.g.*
       ``using`` and ``with`` clauses), and

     * *mode* is one of ``"file"`` or ``"pipe"`` (default is ``"pipe"``; see
       :meth:`Gnuplot.plot` for details).

   For example,
   ::

     plot = xnuplot.Plot()
     plot.append("sin(x) notitle")
     plot.append(("0 0\n3.14 1.0",
                  "using linespoints title 'Line segment'"))

   .. highlight:: gnuplot

   This is roughly equivalent to the following Gnuplot command::

     plot sin(x) notitle, \
          'line.dat' using linespoints title 'Line segment'

   where the contents of ``line.dat`` is
   ::

     0 0
     3.14 1.0

   .. highlight:: python

   Except that with Xnuplot, you can alter the plot items without having to
   reenter the unchanged ones::

     plot.pop(0) # This removes the sin(x) but keeps the line segment.


   .. note::

      ``Plot`` objects always use Gnuplot's ``plot`` command to render the
      plot. To plot bivariate data (using the ``splot`` command), use the
      analogous :class:`SPlot` class.


   .. attribute:: autorefresh

      If ``True``, refresh the plot (reissue the Gnuplot ``plot`` command)
      every time the plot is modified.


   .. attribute:: description

      A description for the plot. This can be set to any value, and is saved
      together with the plot by the :meth:`save` method.


   .. attribute:: size

      Used when part of a :class:`Multiplot` to set the size of this plot. A
      pair of scale factors (x, y).


   .. attribute:: origin

      Used when part of a :class:`Multiplot` to set the origin of this plot. A
      pair of screen coordinates (x, y).


   .. method:: __call__(command[, dataitems...])

      Execute a Gnuplot command.

      :arg str command: the command to execute

      :arg dataitems: data to pass to Gnuplot (see :meth:`RawGnuplot.__call__`)
      :type dataitems: keyword arguments

      :returns: the output from the command

      For example,
      ::

        plot = xnuplot.Plot()
        plot("set style data linespoints")

      .. note::

         It is usually not necessary to use the low level data passing
         interface provided by the *dataitems* arguments. Instead, use the
         sequence methods (:meth:`append`, etc.) to plot data and :meth:`fit`
         to perform curve fitting.


   .. method:: interact()

      Interact with the Gnuplot command line.
      
      This is handy during interactive use for quickly setting or inspecting
      various plot attributes, reading the Gnuplot online documentation, or for
      using the mouse to manipulate the plot (when using a mouse-enabled
      terminal such as the x11 terminal).

      Type :kbd:`Control-]` to exit interact mode and return to Python.


   .. method:: refresh()

      Draw or redraw the plot with the current plot items.


   .. method:: save(file)

      Save the plot to a file.

      :arg file: the file to save to.
      :type file: string (filename) or file object

      The saved file will contain the current settings of the attached Gnuplot
      process as well as the plot items contained in the ``Plot`` object. Saved
      plots can be loaded with :func:`load` or by using the :program:`xnuplot`
      command line tool.


   .. method:: clone()

      Create a duplicate Plot object, sharing the same plot items but with its
      own Gnuplot process. Gnuplot settings and variables are preserved.


   .. method:: close()

      Terminate the attached Gnuplot process. This is called automatically when
      the ``Plot`` object is deleted (or garbage-collected).


   .. method:: fit(data, expr, via[, ranges, limit, maxiter, start_lambda, lambda_factor])

      Perform curve fitting using Gnuplot's ``fit`` command.

      :arg data: a plot item specifying the data to fit to
      :type data: tuple or :class:`PlotData`
      :arg str expr: the Gnuplot expression for the function to fit
      :arg via: the variables to float (and, optionally, their initial values):
                *e.g.* ``"a, b"``, ``("a", "b")``, or ``{"a": 0.1, "b": 3.0}``
      :type via: str, tuple, or dict
      :arg str ranges: the range(s) to fit over (this is passed verbatim to
                       Gnuplot): *e.g.* ``"[0.0:1.0]"``
      :arg limit: set Gnuplot's FIT_LIMIT
      :arg maxiter: set Gnuplot's FIT_MAXITER
      :arg start_lambda: set Gnuplot's FIT_START_LAMBDA
      :arg lambda_factor: set Gnuplot's FIT_LAMBDA_FACTOR

      :returns: (*params*, *errors*, *log*), where

                - *params* is a dictionary containing the fit parameter values,
                - *errors* is a dictionary containing the errors of the fit for
                  each parameter, and
                - *log* is the human-readable report from the ``fit`` command.


.. class:: SPlot([autorefresh=True, persist=False, description=None, kwargs...])

   An interface to a Gnuplot bivariate (surface) plot.
   
   Usage is exactly the same as :class:`Plot`, except that the items are
   plotted using Gnuplot's ``splot`` command instead of the ``plot`` command.


.. class:: Multiplot([autorefresh=True, persist=False, description=None, kwargs...])

   An encapsulation of Gnuplot's multiplot facility (see ``set multiplot`` in
   the Gnuplot manual).

   The constructor parameters are the same as with the :class:`Plot` and
   :class:`SPlot` classes, with whom ``Multiplot`` shares the following
   attributes and methods: :attr:`~Plot.autorefresh`,
   :attr:`~Plot.description`, :meth:`~Plot.__call__`, :meth:`~Plot.interact`,
   :meth:`~Plot.refresh`, :meth:`~Plot.save`, :meth:`clone` (see below), and
   :meth:`~Plot.close`.

   ``Multiplot`` also inherits from ``list``, but as items holds whole
   :class:`Plot` and :class:`SPlot` instances (as subplots), rather than plot
   items. When the subplots are modified, the change is reflected in the
   multiplot (if ``autorefresh`` is set to True on the multiplot).

   The position and scaling of the subplots are determined by the subplots'
   :attr:`~Plot.origin` and :attr:`~Plot.size` attributes.

   :meth:`Multiplot.save` will save the multiplot together with all of its
   subplots.

   .. method:: clone([recursive=False, kwargs...])

      Clone the multiplot. If recursive is True, each subplot is cloned and
      placed in the new multiplot; otherwise, the cloned multiplot shares all
      of its subplots with the original.


.. class:: GridMultiplot(rows, cols[, rowsfirst=True, upwards=False, title=None, scale=None, offset=None, kwargs...])

   An encapsulation of Gnuplot's multiplot facility using a grid layout.

   This is a version of :class:`Multiplot` that uses Gnuplot's ``set multiplot
   layout`` option.

   :arg int rows: number of rows in the multiplot grid

   :arg int cols: number of columns in the multiplot grid

   :arg bool rowsfirst: if true, fill the grid with subplots in row-first order

   :arg bool upwards: if true, start at the bottom row (or the bottom cell of
                      the first column); else, start at the top row

   :arg str title: add a title for the multiplot

   :arg tuple scale: scale factors (xscale, yscale) applied to each subplot

   :arg tuple offset: offset (in screen coordinates) applied to each subplot

   ``GridMultiplot`` shares all methods with :class:`Multiplot`, but has
   additional attributes corresponding to the constructor arguments.

   .. attribute:: rows

      The number of rows in the multiplot grid.

   .. attribute:: cols

      The number of columns in the multiplot grid.

   .. attribute:: rowsfirst

      If true, the grid will be filled with subplots in row-first order; else,
      in column-first order.

   .. attribute:: upwards

      If true, the grid will be filled from bottom to top, starting with the
      bottom row (or the bottom cell of the first column, if :attr:`rowsfirst`
      is ``True``); else, the grid will be filled from top to bottom.

   .. attribute:: title

      The title for the multiplot.

   .. attribute:: scale

      A pair of scale factors (x, y) that are applied to each subplot.

   .. attribute:: offset

      A pair of offsets (x, y) that are applied to each subplot.


.. function:: load(file[, autorefresh=True, persist=False, class_=None])

   Load a plot archived by the :meth:`Plot.save` or :meth:`SPlot.save` method.

   :arg file: the file containing the saved plot to load
   :type file: string (filename) or file object

   :arg bool autorefresh: whether to automatically replot when plot items are
                          added, removed, or replaced or the plot is otherwise
                          modified

   :arg bool persist: whether the plot window (if any) should stay open after
                      Gnuplot quits (*i.e.* after the :class:`Plot` object is
                      deleted)

   :arg class class\_: the class to use for the returned plot object (defaults
                       to :class:`Plot`, :class:`SPlot`, :class:`Multiplot`, or
                       :class:`GridMultiplot`, depending on the contents of
                       *file*)

   The *class_* argument is useful if, for example, you want to load a saved
   plot as a :class:`numplot.Plot` object.

.. function:: closeall()

   Close all xnuplot plots and terminate all interfaced Gnuplot processes.


.. exception:: FileFormatError

   Raised by :func:`load` when the given file does not have the expected
   format.

