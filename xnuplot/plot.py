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

_MAGIC = "xnuplot-saved-session"

class FileFormatError(RuntimeError):
    """Raised if a saved xnuplot session file has the wrong format."""

class _ObservedList(list):
    # A list that calls self.refresh() upon modification when self.autorefresh
    # is true..
    autorefresh = True
    def refresh(self):
        pass

    # Replace all list-modifying methods with wrapped versions that call
    # self.refresh() when self.autorefresh is true.
    @staticmethod
    def _with_autorefresh(func):
        def call_and_refresh(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
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


class Plot(_Gnuplot, _ObservedList):
    _plotmethod = _Gnuplot.plot
    _plotcmd = "plot" # for save()

    def __init__(self, autorefresh=True, description=None, **kwargs):
        _ObservedList.__init__(self, [])
        _Gnuplot.__init__(self, **kwargs)
        self.autorefresh = autorefresh
        self.description = description
        self._refreshing = False

    __call__ = _ObservedList._with_autorefresh(_Gnuplot.__call__)

    def clear(self):
        self[:] = []

    def keep(self, indices):
        if not isinstance(indices, collections.Sequence):
            indices = (indices,)
        self[:] = [self[i] for i in indices]

    def refresh(self):
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

    def save(self, file):
        items = []
        for item in self:
            if isinstance(item, basestring):
                items.append(item)
            else:
                if isinstance(item, tuple):
                    item = PlotData(*item)
                items.append((item.data, item.options, item.mode))

        script = self("save '-'").split("\n")
        script = [line for line in script if len(line) and
                  not line.lstrip().startswith("#") and
                  not line.startswith("plot ") and
                  not line.startswith("splot ") and
                  not line.startswith("GNUTERM =")]
        script = "\n".join(script)

        data = {"magic": _MAGIC, "version": 0,
                "description": self.description,
                "script": script,
                "plot": self._plotcmd, "items": items}

        if hasattr(file, "write"):
            pickle.dump(data, file)
        else:
            with open(file, "wb") as f:
                pickle.dump(data, f)

    def __repr__(self):
        classname = self.__class__.__name__
        return "<{0} {1}>".format(classname, _ObservedList.__repr__(self))

class SPlot(Plot):
    _plotmethod = _Gnuplot.splot
    _plotcmd = "splot" # for save()


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
    if data["version"] > 0:
        raise FormatError("file saved by a newer version of xnuplot")

    kwargs = dict(persist=persist, autorefresh=False,
                  description=data.get("description"))
    if class_ is None:
        if data["plot"] == "plot":
            class_ = Plot
        elif data["plot"] == "splot":
            class_ = SPlot
        else:
            raise FormatError("unknown plot type: {0}".format(data["plot"]))
    elif class_._plotcmd != data["plot"]:
        raise TypeError("specified class (%s) does not match plot type (%s) "
                        "of file (%s)" % (class_.__name__, data["plot"],
                                          str(file)))
    plot = class_(**kwargs)

    plot.source(data["script"])
    for item in data["items"]:
        if isinstance(item, basestring):
            plot.append(item)
        else:
            plot.append(PlotData(*item))
    plot.autorefresh = autorefresh
    if autorefresh:
        plot.refresh()
    return plot

