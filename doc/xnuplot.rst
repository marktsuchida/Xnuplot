Package xnuplot
===============

.. module:: xnuplot

Modules:

.. toctree::
   :maxdepth: 1

   gnuplot
   numplot

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
                :class:`xnuplot.gnuplot.Gnuplot` or
                :class:`xnuplot.gnuplot.RawGnuplot` constructors.

   ``Plot`` inherits from ``list``. You can use the standard sequence methods
   (``insert()``, ``append()``, ``pop()``, and others), the ``del`` statement,
   and the indexing operator (``[]``) to add, remove, and replace plot items
   (equivalent to the comma-separated arguments to Gnuplot's ``plot`` command).

   If the :attr:`autorefresh` attribute is set to ``True``, simply changing the
   contents of the ``Plot`` container will automatically update the plot.

   Plot items can be

   - a string (*e.g.* ``"sin(x)"``),

   - an :class:`xnuplot.gnuplot.PlotData` instance, or

   - a tuple, (*data* [, *options* [, *mode*]]), which is used as the arguments
     to construct a ``PlotData`` object, where

     * *data* can either be a string in a format that Gnuplot understands,
       or an object that exposes binary data (also must be in a format handled
       by Gnuplot) through the buffer protocol,

     * *options* is a string containing Gnuplot plot options (*e.g.*
       ``using`` and ``with`` clauses), and

     * *mode* is one of ``"file"`` or ``"pipe"`` (default is ``"pipe"``; see
       :meth:`xnuplot.gnuplot.Gnuplot.plot` for details).

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


   .. method:: __call__(command[, dataitems...])

      Execute a Gnuplot command.

      :arg str command: the command to execute

      :arg dataitems: data to pass to Gnuplot (see
                      :meth:`xnuplot.gnuplot.RawGnuplot.__call__`)
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


   .. method:: close()

      Terminate the attached Gnuplot process. This is called automatically when
      the ``Plot`` object is deleted (or garbage-collected).


   .. method:: fit(data, expr, via[, ranges, limit, maxiter, start_lambda, lambda_factor])

      Perform curve fitting using Gnuplot's ``fit`` command.

      :arg data: a plot item specifying the data to fit to
      :type data: tuple or :class:`xnuplot.gnuplot.PlotData`
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


.. function:: load(file[, autorefresh=True, persist=False])

   Load a plot archived by the :meth:`Plot.save` or :meth:`SPlot.save` method.

   :arg file: the file containing the saved plot to load
   :type file: string (filename) or file object

   :arg bool autorefresh: whether to automatically replot when plot items are
                          added, removed, or replaced or the plot is otherwise
                          modified

   :arg bool persist: whether the plot window (if any) should stay open after
                      Gnuplot quits (*i.e.* after the :class:`Plot` object is
                      deleted)

   :rtype: :class:`Plot` or :class:`SPlot`, depending on the plot contained in
           *file*

   :raises: :exc:`xnuplot.plot.FileFormatError` if *file* is not in the expected
            format


.. function:: closeall()

   Close all xnuplot plots and terminate all interfaced Gnuplot processes.
   (This acts on :class:`xnuplot.gnuplot.Gnuplot` and
   :class:`xnuplot.gnuplot.RawGnuplot` objects as well as :class:`Plot` and
   :class:`SPlot` objects.)
