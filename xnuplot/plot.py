# Copyright (c) 2011 Mark A. Tsuchida
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

from .gnuplot import Gnuplot as _Gnuplot, PlotData, GnuplotError
import collections
import cPickle as pickle
import warnings

_MAGIC = "xnuplot-saved-session"
_PLOT_FILE_VERSION = 0
_MULTIPLOT_FILE_VERSION = 1
_LOADABLE_FILE_VERSION = 1

class FileFormatError(RuntimeError):
    """Raised if a saved xnuplot session file has the wrong format."""

class _ObservedList(list):
    # A list that calls self.refresh() upon modification when self.autorefresh
    # is true.
    autorefresh = True
    def refresh(self):
        pass

    def clear(self):
        self[:] = []

    def keep(self, indices):
        if not isinstance(indices, collections.Sequence):
            indices = (indices,)
        self[:] = [self[i] for i in indices]

    # Replace all list-modifying methods with wrapped versions that call
    # self.refresh() when self.autorefresh is true.
    @staticmethod
    def _with_autorefresh(func):
        def call_and_refresh(self, *args, **kwargs):
            if hasattr(self, "notify_change"):
                old_contents = list(self)
            result = func(self, *args, **kwargs)
            if hasattr(self, "notify_change"):
                new_contents = list(self)
                if ([id(o) for o in new_contents] !=
                    [id(o) for o in old_contents]):
                    self.notify_change(old_contents, new_contents)
            if self.autorefresh:
                self.refresh()
            return result
        return call_and_refresh
    _modifying_methods = ["append", "extend",
                          "insert", "pop",
                          "remove",
                          "reverse", "sort",
                          "__setitem__", "__delitem__",
                          "__setslice__", "__delslice__",
                          "__iadd__", "__imul__"]

for name in _ObservedList._modifying_methods:
    # This cannot be done within the class definition, because there is no way
    # to access the class object. (Actually, vars()[name] appears to work, but
    # the documentation recommends against such usage.)
    setattr(_ObservedList,
            name,
            _ObservedList._with_autorefresh(getattr(list, name)))


class _BasePlot(_Gnuplot):
    def environment_script(self):
        script = self("save '-'").split("\n")
        script = [line for line in script if len(line) and
                  not line.lstrip().startswith("#") and
                  not line.startswith("plot ") and
                  not line.startswith("splot ") and
                  not line.startswith("GNUTERM =")]
        script = "\n".join(script)
        return script

    def save(self, file):
        data = self._data_dict() # _data_dict() defined by subclasses.
        data["magic"] = _MAGIC

        if hasattr(file, "write"):
            pickle.dump(data, file)
        else:
            with open(file, "wb") as f:
                pickle.dump(data, f)


class Plot(_BasePlot, _ObservedList):
    _plotmethod = _Gnuplot.plot
    _plotcmd = "plot" # for save()

    def __init__(self, autorefresh=True, description=None, **kwargs):
        _ObservedList.__init__(self, [])
        _Gnuplot.__init__(self, **kwargs)
        self.autorefresh = autorefresh
        self.description = description
        self._refreshing = False

        # Multiplot support.
        self.parents = []
        self._size = None
        self._origin = None

    __call__ = _ObservedList._with_autorefresh(_Gnuplot.__call__)

    @property
    def size(self):
        return self._size
    @size.setter
    @_ObservedList._with_autorefresh
    def size(self, size):
        self._size = size

    @property
    def origin(self):
        return self._origin
    @origin.setter
    @_ObservedList._with_autorefresh
    def origin(self, origin):
        self._origin = origin

    def refresh(self):
        for parent in self.parents:
            if parent.autorefresh:
                parent.refresh()

        # Guard against infinite recursion.
        if self._refreshing or not self.isalive():
            return
        self._refreshing = True
        try:
            if len(self):
                self._plotmethod(*self)
            else:
                self("clear")
        finally:
            self._refreshing = False

    def fit(self, data, expr, via, ranges=None,
            limit=None, maxiter=None, start_lambda=None, lambda_factor=None):
        # Suppress autorefresh while we execute a number of Gnuplot commands.
        self._refreshing = True
        skip_autorefresh = False
        try:
            return self._fit(data, expr, via, ranges, limit, maxiter,
                             start_lambda, lambda_factor)
        except:
            skip_autorefresh = True
        finally:
            self._refreshing = False
            if not skip_autorefresh and self.autorefresh:
                self.refresh()

    def _fit(self, data, expr, via, ranges,
             limit, maxiter, start_lambda, lambda_factor):
        if isinstance(via, basestring):
            vars = tuple(v.strip() for v in via.split(","))
        if isinstance(via, collections.Mapping):
            for var in via:
                result = self("{0} = {1}".format(var, via[var]))
                if len(result):
                    raise GnuplotError("cannot set Gnuplot variable "
                                       "`{0}' to `{1}'". format(var, via[var]))
            vars = sorted(via.keys())
        else:
            vars = tuple(via)
        via = ", ".join(vars)

        self("FIT_LIMIT = {0:e}".format(limit if limit is not None else 1e-5))
        self("FIT_MAXITER = {0:d}".format(maxiter or 0))
        self("FIT_START_LAMBDA = {0:e}".format(start_lambda or 0.0))
        self("FIT_LAMBDA_FACTOR = {0:e}".format(lambda_factor or 0.0))

        self("set fit logfile '/dev/null' errorvariables")
        log = super(Plot, self).fit(data, expr, via, ranges).strip() + "\n"
        self("unset fit")

        params = dict()
        errors = dict()
        def get_var(name):
            value = self("print {0}".format(name)).strip()
            try:
                return float(value)
            except:
                return None
        for var in vars:
            params[var] = get_var(var)
            errors[var] = get_var(var + "_err")

        return params, errors, log

    def _data_dict(self):
        items = []
        for item in self:
            if isinstance(item, basestring):
                items.append(item)
            else:
                if isinstance(item, tuple):
                    item = PlotData(*item)
                items.append((item.data, item.options, item.mode))

        data = {
                "version": _PLOT_FILE_VERSION,
                "description": self.description,
                "plot": self._plotcmd,
                "items": items,
                "script": self.environment_script(),
               }

        if self.size:
            data["size"] = self.size
        if self.origin:
            data["origin"] = self.origin

        return data

    def __repr__(self):
        classname = self.__class__.__name__
        return "<{0} {1}>".format(classname, _ObservedList.__repr__(self))

class SPlot(Plot):
    _plotmethod = _Gnuplot.splot
    _plotcmd = "splot" # for save()


class Multiplot(_BasePlot, _ObservedList):
    def __init__(self, autorefresh=True, description=None, **kwargs):
        _ObservedList.__init__(self, [])
        _Gnuplot.__init__(self, **kwargs)
        self.autorefresh = autorefresh
        self.description = description
        self._refreshing = False

    __call__ = _ObservedList._with_autorefresh(_Gnuplot.__call__)

    def _multiplot_command(self):
        return "set multiplot"

    def _save_origin_and_size(self):
        message = self("show origin").strip()
        remainder, ori_y = message.split(",")
        ori_x = remainder.strip().split()[-1]
        self._saved_origin = tuple(int(o.strip()) for o in (ori_x, ori_y))

        message = self("show size").strip()
        message1, message2 = (m.strip() for m in message.split("\n"))
        remainder, siz_y = message1.split(",")
        siz_x = remainder.strip().split()[-1]
        self._saved_size = tuple(int(s.strip()) for s in (siz_x, siz_y))
        if "No attempt" in message2:
            self._saved_size_ratio = None
        else:
            ratio_sign = 1
            if "LOCKED" in message2:
                ratio_sign = -1
            ratio = int(message2.split(":")[-2].strip().split()[-1])
            self._saved_size_ratio = ratio_sign * ratio

    def _restore_origin_and_size(self):
        self("set origin %e, %e" % self._saved_origin)
        if self._saved_size_ratio is None:
            ratio_arg = "noratio"
        else:
            ratio_arg = "ratio %e" % self._saved_size_ratio
        self("set size %s %e, %e" % ((ratio_arg,) + self._saved_size))

    def refresh(self):
        # Guard against infinite recursion.
        if self._refreshing or not self.isalive():
            return
        self._refreshing = True
        try:
            if len(self):
                self._save_origin_and_size()
                self._saved_prompt = self.gp_prompt
                self.gp_prompt = "multiplot> "
                self(self._multiplot_command())
                try:
                    for plot in self:
                        if len(plot) == 0:
                            # There is no way to insert an empty plot into
                            # a multiplot.
                            warnings.warn("skipping empty plot")
                            continue

                        script = plot.environment_script().split("\n")
                        script = [line for line in script if
                                  not line.startswith("set origin ") and
                                  not line.startswith("set size ")]
                        self.source("\n".join(script))

                        if plot.size:
                            self("set size %e, %e" % plot.size)
                        if plot.origin:
                            self("set origin %e, %e" % plot.origin)

                        plotmethod = plot._plotmethod.im_func
                        plotmethod(self, *plot)
                finally:
                    self.gp_prompt = self._saved_prompt
                    self("unset multiplot")
                    self._restore_origin_and_size()
            else:
                self("clear")
        finally:
            self._refreshing = False

    def notify_change(self, old, new):
        new_ids = [id(p) for p in new]
        old_ids = [id(p) for p in old]
        for plot in old:
            if id(plot) not in new_ids:
                plot.parents = [p for p in plot.parents if p is not self]
        for plot in new:
            if id(plot) not in old_ids:
                plot.parents.append(self)

    def _data_dict(self):
        subplots = []
        for plot in self:
            subplots.append(plot._data_dict())

        data = {
                "version": _MULTIPLOT_FILE_VERSION,
                "description": self.description,
                "plot": "multiplot",
                "items": subplots,
                "script": self.environment_script(),
               }

        return data

    def __repr__(self):
        classname = self.__class__.__name__
        return "<{0} {1}>".format(classname, _ObservedList.__repr__(self))


class GridMultiplot(Multiplot):
    def __init__(self, rows, cols, rowsfirst=True, upwards=False, title=None,
                 scale=None, offset=None, **kwargs):
        Multiplot.__init__(self, **kwargs)
        self._rows = rows; self._cols = cols
        self._rowsfirst = rowsfirst; self._upwards = upwards
        self._title = title
        self._scale = scale; self._offset = offset

    @property
    def rows(self):
        return self._rows
    @rows.setter
    @_ObservedList._with_autorefresh
    def rows(self, rows):
        self._rows = rows

    @property
    def cols(self):
        return self._cols
    @cols.setter
    @_ObservedList._with_autorefresh
    def cols(self, cols):
        self._cols = cols

    @property
    def rowsfirst(self):
        return self._rowsfirst
    @rowsfirst.setter
    @_ObservedList._with_autorefresh
    def rowsfirst(self, rowsfirst):
        self._rowsfirst = rowsfirst

    @property
    def upwards(self):
        return self._upwards
    @upwards.setter
    @_ObservedList._with_autorefresh
    def upwards(self, upwards):
        self._upwards = upwards

    @property
    def title(self):
        return self._title
    @title.setter
    @_ObservedList._with_autorefresh
    def title(self, title):
        self._title = title

    @property
    def scale(self):
        return self._scale
    @scale.setter
    @_ObservedList._with_autorefresh
    def scale(self, scale):
        self._scale = scale

    @property
    def offset(self):
        return self._offset
    @offset.setter
    @_ObservedList._with_autorefresh
    def offset(self, offset):
        self._offset = offset

    def _multiplot_command(self):
        args = [("rowsfirst" if self.rowsfirst else "columnsfirst"),
                ("upwards" if self.upwards else "downwards")]
        if self.title:
            args.append("title " + self.quote(self.title))
        if self.scale:
            args.append("scale " + ", ".join(str(s) for s in self.scale))
        if self.offset:
            args.append("offset " + ", ".join(str(s) for s in self.offset))
        args = " ".join(args)
        return "set multiplot layout %d, %d %s" % (self.rows, self.cols, args)

    def _data_dict(self):
        data = Multiplot._data_dict(self)

        data["plot"] = "gridmultiplot"
        data["grid_rows"] = self.rows
        data["grid_cols"] = self.cols
        data["grid_rowsfirst"] = self.rowsfirst
        data["grid_upwards"] = self.upwards
        if self.title:
            data["grid_title"] = self.title
        if self.scale:
            data["grid_scale"] = self.scale
        if self.offset:
            data["grid_offset"] = self.offset

        return data


def load(file, persist=False, autorefresh=True, class_=None):
    if hasattr(file, "read"):
        data = pickle.load(file)
    else:
        with open(file) as f:
            data = pickle.load(f)

    try:
        assert data["magic"] == _MAGIC
    except:
        raise FormatError("does not appear to be an xnuplot session file")

    if data["plot"] in ("plot", "splot"):
        plot = _load_plot(data, persist, class_)
    else:
        plot = _load_multiplot(data, persist, class_)

    plot.autorefresh = autorefresh
    if data["plot"] in ("multiplot", "gridmultiplot"):
        for p in plot:
            p.autorefresh = autorefresh
    if autorefresh:
        plot.refresh()
    return plot


def _load_plot(data, persist=False, class_=None):
    if data["version"] > _LOADABLE_FILE_VERSION:
        raise FormatError("file saved by a newer version of xnuplot")

    kwargs = dict(persist=persist, autorefresh=False,
                  description=data.get("description"))

    if data["plot"] == "plot":
        fileclass = Plot
    elif data["plot"] == "splot":
        fileclass = SPlot
    else:
        raise FormatError("unknown plot type: {0}".format(data["plot"]))

    if class_ is None:
        class_ = fileclass
    elif not issubclass(class_, fileclass):
        raise TypeError("specified class (%s) does not match plot type (%s) "
                        "of file (%s)" % (class_.__name__, data["plot"],
                                          str(file)))
    plot = class_(**kwargs)

    if "script" in data:
        plot.source(data["script"])

    if "size" in data:
        plot.size = data["size"]
    if "origin" in data:
        plot.origin = data["origin"]

    for item in data["items"]:
        if isinstance(item, basestring):
            plot.append(item)
        else:
            plot.append(PlotData(*item))

    return plot

def _load_multiplot(data, persist=False, class_=None):
    if data["version"] > _LOADABLE_FILE_VERSION:
        raise FormatError("file saved by a newer version of xnuplot")

    kwargs = dict(persist=persist, autorefresh=False,
                  description=data.get("description"))

    if data["plot"] == "multiplot":
        fileclass = Multiplot
    elif data["plot"] == "gridmultiplot":
        fileclass = GridMultiplot
        kwargs["rows"] = data["grid_rows"]
        kwargs["cols"] = data["grid_cols"]
    else:
        raise FormatError("unknown plot type: {0}".format(data["plot"]))

    if class_ is None:
        class_ = fileclass
    elif not issubclass(class_, fileclass):
        raise TypeError("specified class (%s) does not match plot type (%s) "
                        "of file (%s)" % (class_.__name__, data["plot"],
                                          str(file)))
    plot = class_(**kwargs)

    plot.source(data["script"])

    if class_ is GridMultiplot:
        if "grid_rowsfirst" in data:
            plot.rowsfirst = data["grid_rowsfirst"]
        if "grid_upwards" in data:
            plot.upwards = data["grid_upwards"]
        if "grid_title" in data:
            plot.title = data["grid_title"]
        if "grid_scale" in data:
            plot.scale = data["grid_scale"]
        if "grid_offset" in data:
            plot.offset = data["grid_offset"]

    for item in data["items"]:
        subplot = _load_plot(item, persist)
        plot.append(subplot)

    return plot

