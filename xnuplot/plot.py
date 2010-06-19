from .gnuplot import Gnuplot

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

    def __init__(self, command=None, persist=False, autorefresh=True):
        _ObservedList.__init__(self, [])
        Gnuplot.__init__(self, command, persist)
        self.autorefresh = autorefresh
        self._refreshing = False

    __call__ = _ObservedList._with_autorefresh(Gnuplot.__call__)

    def refresh(self):
        # Guard against infinite recursion.
        if self._refreshing:
            return
        self._refreshing = True
        try:
            if len(self):
                self._plotmethod(*self)
            else:
                self("clear")
        finally:
            self._refreshing = False

    def __repr__(self):
        classname = self.__class__.__name__
        return "<%s %s>" % (classname, _ObservedList.__repr__(self))

class SPlot(Plot):
    _plotmethod = Gnuplot.splot

