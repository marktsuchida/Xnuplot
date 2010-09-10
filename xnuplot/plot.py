from .gnuplot import Gnuplot, PlotData as _PlotData
import cPickle as _pickle

_MAGIC = "xnuplot-saved-session"

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


class Plot(Gnuplot, _ObservedList):
    _plotmethod = Gnuplot.plot
    _plotcmd = "plot" # for save()

    def __init__(self, autorefresh=True, **kwargs):
        _ObservedList.__init__(self, [])
        Gnuplot.__init__(self, **kwargs)
        self.autorefresh = autorefresh
        self._refreshing = False

    __call__ = _ObservedList._with_autorefresh(Gnuplot.__call__)

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

    def save(self, file):
        items = []
        for item in self:
            if isinstance(item, basestring):
                items.append(item)
            else:
                if isinstance(item, tuple):
                    item = _PlotData(*item)
                items.append((item.data, item.options, item.mode))

        script = self("save '-'").split("\n")
        script = [line for line in script if len(line) and
                  not line.lstrip().startswith("#") and
                  not line.startswith("plot ") and
                  not line.startswith("splot ") and
                  not line.startswith("GNUTERM =")]
        script = "\n".join(script)

        data = {"magic": _MAGIC, "version": 0,
                "script": script,
                "plot": self._plotcmd, "items": items}

        if hasattr(file, "write"):
            _pickle.dump(data, file)
        else:
            with open(file, "wb") as f:
                _pickle.dump(data, f)

    def __repr__(self):
        classname = self.__class__.__name__
        return "<%s %s>" % (classname, _ObservedList.__repr__(self))

class SPlot(Plot):
    _plotmethod = Gnuplot.splot
    _plotcmd = "splot" # for save()

class FormatError(Exception): pass

def load(file, persist=False, autorefresh=True):
    if hasattr(file, "read"):
        data = _pickle.load(file)
    else:
        with open(file) as f:
            data = _pickle.load(f)

    try:
        if data["magic"] != _MAGIC:
            raise Exception()
    except:
        raise FormatError("does not appear to be an xnuplot session file")
    if data["version"] > 0:
        raise FormatError("file saved by a newer version of xnuplot")

    kwargs = dict(persist=persist, autorefresh=False)
    if data["plot"] == "plot":
        plot = Plot(**kwargs)
    elif data["plot"] == "splot":
        plot = SPlot(**kwargs)
    else:
        raise FormatError("unknown plot type: %s" % data["plot"])

    plot(data["script"])
    for item in data["items"]:
        if isinstance(item, basestring):
            plot.append(item)
        else:
            plot.append(_PlotData(*item))
    plot.autorefresh = autorefresh
    return plot

