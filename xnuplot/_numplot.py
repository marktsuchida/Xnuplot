# Copyright (c) 2011-2012 Mark A. Tsuchida
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to
# deal in the Software without restriction, including without limitation the
# rights to use, copy, modify, merge, publish, distribute, sublicense, and/or
# sell copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING
# FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS
# IN THE SOFTWARE.

from . import PlotData
from ._plot import Plot as _Plot, SPlot as _SPlot
import numpy

def array(arr, options=None, coord_options=None, using=None):
    """Return a binary array plot data item for a NumPy array."""
    return _array_or_record(arr, "array", options,
                            coord_options=coord_options, using=using)

def record(arr, options=None, using=None):
    """Return a binary record plot data item for a NumPy array."""
    return _array_or_record(arr, "record", options, using=using)

def matrix(arr, xcoords, ycoords, options=None):
    """Return a binary matrix plot data item for a NumPy array."""
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
    return PlotData(m, options, mode="file")

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

    return PlotData(a, options)

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

