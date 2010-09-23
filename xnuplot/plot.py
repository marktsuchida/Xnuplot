from .gnuplot import Gnuplot as _Gnuplot, PlotData, GnuplotError
import collections
import cPickle as pickle

_MAGIC = "xnuplot-saved-session"

class FormatError(RuntimeError):
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
        """Perform a Gnuplot `fit'.

        data          - a PlotData instance, or a tuple to be used to construct
                        one
        expr          - the Gnuplot expression for the function to fit to
        via           - a string (e.g. "a, b"), a tuple (e.g. ("a", "b")), or a
                        dict with initial parameter values (e.g. dict(a=0.1,
                        b=3.0))
        ranges        - a string specifying the ranges (passed unmodified to
                        Gnuplot)
        limit         - set Gnuplot's FIT_LIMIT
        maxiter       - set Gnuplot's FIT_MAXITER
        start_lambda  - set Gnuplot's FIT_START_LAMBDA
        lambda_factor - set Gnuplot's FIT_LAMBDA_FACTOR

        Returns: (params, errors, log) where params and errors are dicts whose
                 keys are the parameter names given by the via argument.
        """
        # TODO Support (as kwargs) limit, maxiter, start_lambda, and
        # lambda_factor.

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


def load(file, persist=False, autorefresh=True):
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
    if data["plot"] == "plot":
        plot = Plot(**kwargs)
    elif data["plot"] == "splot":
        plot = SPlot(**kwargs)
    else:
        raise FormatError("unknown plot type: {0}".format(data["plot"]))

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

