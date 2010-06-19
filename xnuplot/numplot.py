import numpy

class _PlotItem(object):
    # Compatible with xnuplot.gnuplot.PlotItem, but with an array for the data.
    def __init__(self, array, options=None, use_real_file=False):
        # The array must be in the correct binary format.
        self.array = array
        self.options = options
        self.use_real_file = use_real_file
    @property
    def data(self):
        return self.array.data

def array(arr, options=None):
    """Return a plot item in `binary array' format.

    The returned tuple can be used as an argument to the plot(), splot(), and
    replot() methods of xnuplot.gnuplot.Gnuplot.
    """
    return _array_or_record(arr, "array", options)

def record(arr, options=None):
    """Return a plot item in `binary record' format.

    The returned tuple can be used as an argument to the plot(), splot(), and
    replot() methods of xnuplot.gnuplot.Gnuplot.
    """
    return _array_or_record(arr, "record", options)

def matrix(arr, xcoords, ycoords, options=None):
    """Return a plot item in `binary matrix' format.

    The returned tuple can be used as an argument to the plot(), splot(), and
    replot() methods of xnuplot.gnuplot.Gnuplot.
    """
    a = numpy.asarray(arr)
    if a.ndim != 2:
        raise ValueError("array for Gnuplot matrix must have 2 dimensions")
    # `binary matrix' requires float32.
    m = numpy.empty((a.shape[0] + 1, a.shape[1] + 1),
                    dtype=numpy.float32, order="C")
    m[0, 0] = a.shape[1]
    m[0, 1:] = xcoords
    m[1:, 0] = ycoords
    m[1:, 1:] = a
    options = " ".join(filter(None, ["binary", "matrix", options]))
    # Gnuplot (as of 4.4.0) fseek()s to the end of a `binary matrix' datafile
    # before reading the actual data, so sending the data through a pipe
    # doesn't work. Therefore, use real file (see xnuplot.gnuplot.PlotItem).
    return _PlotItem(m, options, use_real_file=True)

def _array_or_record(arr, array_or_record, options=None):
    a = numpy.asarray(arr)
    shape = ",".join(str(s) for s in reversed(a.shape))
    dataspec = "%s=(%s)" % (array_or_record, shape)
    a, format = _gnuplot_array_and_format(a)
    byteorder = _gnuplot_byteorder(a.dtype)
    endian = (None if byteorder == "default" else "endian=%s" % byteorder)
    a = numpy.require(a, requirements="C")
    options = " ".join(filter(None, ["binary", dataspec,
                                     format, endian, options]))
    return _PlotItem(a, options)

def _gnuplot_array_and_format(a):
    # Get the corresponding Gnuplot format, converting a if necessary.
    try:
        typespec = _gnuplot_type_for_dtype(a.dtype)
    except TypeError:
        if a.dtype.type == numpy.bool_:
            a = a.astype(numpy.uint8)
        else:
            a = a.astype(numpy.float32)
        typespec = _gnuplot_type_for_dtype(a.dtype)
    return a, "format='%%%s'" % typespec

def _gnuplot_type_for_dtype(numpy_dtype):
    t = numpy_dtype.type
    if t == numpy.uint8: return "uint8"
    elif t == numpy.uint16: return "uint16"
    elif t == numpy.uint32: return "uint32"
    elif t == numpy.uint64: return "uint64"
    elif t == numpy.int8: return "int8"
    elif t == numpy.int16: return "int16"
    elif t == numpy.int32: return "int32"
    elif t == numpy.int64: return "int64"
    elif t == numpy.float32: return "float32"
    elif t == numpy.float64: return "float64"
    else: raise TypeError("cannot convert %s to Gnuplot type" % str(t))

def _gnuplot_byteorder(numpy_dtype):
    if numpy_dtype.type in (numpy.uint8, numpy.int8): return "default"
    e = numpy_dtype.byteorder
    if e == "=": return "default"
    elif e == ">": return "big"
    elif e == "<": return "little"
    else: raise TypeError("cannot get byte order of NumPy array")
