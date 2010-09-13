from . import gnuplot
from . import Plot as _Plot, SPlot as _SPlot
import numpy

def array(arr, options=None, coord_options=None, using=None):
    """Return a plot item in `binary array' format.

    arr must be ndim >= 2, and the last dimension corresponds to the `using'
    items (e.g. if arr.shape[-1] == 3, you can use `using=(1, 0, 2)').

    options       - Gnuplot plotting options (axes, title, with)
    coord_options - Gnuplot `binary array' coordinate generation options (dx,
                    dy, dz, flipz, flipy, flipz, origin, center, rotate,
                    perpendicular)
    using         - tuple specifying the Gnuplot `using' list, but with
                    zero-based indexing (along the last axis of arr)

    The returned object can be added to instances of xnuplot.plot.[S]Plot or
    xnuplot.numplot.[S]Plot, or can be used as an argument to the plot(),
    splot(), and replot() methods of xnuplot.gnuplot.Gnuplot,
    """
    return _array_or_record(arr, "array", options,
                            coord_options=coord_options, using=using)

def record(arr, options=None, using=None):
    """Return a plot item in `binary record' format.

    arr must be ndim >= 2, and the last dimension corresponds to the `using'
    items (e.g. if arr.shape[-1] == 3, you can use `using=(1, 0, 2)').

    options       - Gnuplot plotting options (axes, title, with)
    using         - tuple specifying the Gnuplot `using' list, but with
                    zero-based indexing (along the last axis of arr)

    The returned object can be added to instances of xnuplot.plot.[S]Plot or
    xnuplot.numplot.[S]Plot, or can be used as an argument to the plot(),
    splot(), and replot() methods of xnuplot.gnuplot.Gnuplot,
    """
    return _array_or_record(arr, "record", options, using=using)

def matrix(arr, xcoords, ycoords, options=None):
    """Return a plot item in `binary matrix' format.

    The returned object can be added to instances of xnuplot.plot.[S]Plot or
    xnuplot.numplot.[S]Plot, or can be used as an argument to the plot(),
    splot(), and replot() methods of xnuplot.gnuplot.Gnuplot,
    """
    a = numpy.asarray(arr)
    if a.ndim != 2:
        raise ValueError("array for Gnuplot matrix must have ndim == 2")
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
    # doesn't work. Therefore, use real file.
    return gnuplot.PlotData(m, options, mode="file")

def _array_or_record(arr, array_or_record, options,
                     coord_options=None, using=None):
    a = numpy.require(arr, requirements="C")

    # TODO To support structured arrays (arr.dtype.fields is not None), we
    # would allow ndim to be 1 iff arr is a structured array, use the full
    # (reversed) shape of arr for the dataspec, skip the count, and convert the
    # individual field dtypes into a single Gnuplot format string.

    if a.ndim == 1:
        raise ValueError("array for Gnuplot array/record must have ndim >= 2")
    gnuplot_shape = ",".join(str(s) for s in reversed(a.shape[:-1]))
    count = a.shape[-1]

    dataspec = "{0}=({1})".format(array_or_record, gnuplot_shape)
    a, format = _gnuplot_array_and_format(a, count)
    byteorder = _gnuplot_byteorder(a.dtype)
    endian = (None if byteorder == "default" else "endian=" + byteorder)

    if using is not None:
        if numpy.isscalar(using):
            using = (using,)
        using_items = []
        for u in using:
            if isinstance(u, basestring):
                using_items.append(u)
            else:
                if u < 0 or u >= count:
                    raise ValueError("`using' specifier {0} is out of bounds"
                                     " (must be positive and less than {1})".
                                     format(u, count))
                using_items.append(str(u + 1))
        using = "using " + ":".join(using_items)

    options = " ".join(filter(None, ["binary", dataspec, format, endian,
                                     coord_options, using, options]))

    return gnuplot.PlotData(a, options)

def _gnuplot_array_and_format(a, count=1):
    # Get the corresponding Gnuplot format, converting a if necessary.
    try:
        typespec = _gnuplot_type_for_dtype(a.dtype)
    except TypeError:
        if a.dtype.type == numpy.bool_:
            a = a.astype(numpy.uint8)
        else:
            a = a.astype(numpy.float32)
        typespec = _gnuplot_type_for_dtype(a.dtype)
    if count > 1:
        format = "format='%{0}{1}'".format(count, typespec)
    else:
        format = "format='%{0}'".format(typespec)
    return a, format

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
    else: raise TypeError("cannot convert {0} to Gnuplot type".format(t))

def _gnuplot_byteorder(numpy_dtype):
    if numpy_dtype.type in (numpy.uint8, numpy.int8): return "default"
    e = numpy_dtype.byteorder
    if e == "=": return "default"
    elif e == ">": return "big"
    elif e == "<": return "little"
    else: raise TypeError("cannot get byte order of NumPy array")

class _NumPlot(object):
    # A mix-in to add convenience methods.
    def append_array(self, arr, options=None, coord_options=None, using=None):
        self.append(array(arr, options, coord_options, using))
    def insert_array(self, index, arr, options=None,
                     coord_options=None, using=None):
        self.insert(index, array(arr, options, coord_options, using))
    def append_record(self, arr, options=None, using=None):
        self.append(record(arr, options, using))
    def insert_record(self, index, arr, options=None, using=None):
        self.insert(index, record(arr, options, using))
    def append_matrix(self, arr, xcoords, ycoords, options=None):
        self.append(matrix(arr, xcoords, ycoords, options))
    def insert_matrix(self, index, arr, xcoords, ycoords, options=None):
        self.insert(index, matrix(arr, xcoords, ycoords, options))

class Plot(_Plot, _NumPlot): pass

class SPlot(_SPlot, _NumPlot): pass

