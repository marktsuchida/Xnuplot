from .gnuplot import Gnuplot

class _ObservedList(list):
    # A list that calls self.refresh() upon modification (and disallows use of
    # the addition and multiplication operators).

    def __getattribute__(self, name):
        if name in ("append",
                    "extend",
                    "insert",
                    "pop",
                    "remove",
                    "reverse",
                    "sort",
                    "__setitem__",
                    "__delitem__",
                    "__setslice__",
                    "__delslice__",):
            def meth(*args, **kwargs):
                result = list.__getattribute__(self, name)(*args, **kwargs)
                self.refresh()
            return meth
        elif name in ("__add__",
                      "__radd__",
                      "__iadd__",
                      "__mul__",
                      "__rmul__",
                      "__imul__",):
            raise NotImplementedError
        else:
            return list.__getattribute__(self, name)

    def refresh(self):
        pass

class Plot(Gnuplot, _ObservedList):
    def __init__(self, command=None, persist=True):
        _ObservedList.__init__(self, [])
        Gnuplot.__init__(self, command, persist)
        self._autorefresh = False
        self._refreshing = False

    def __call__(self, *args, **kwargs):
        result = Gnuplot.__call__(self, *args, **kwargs)
        if self._autorefresh:
            self.refresh()
        return result

    def refresh(self):
        # Guard against infinite recursion.
        if self._refreshing:
            return
        self._refreshing = True
        try:
            if len(self):
                self.plot(*self)
            else:
                self("clear")
        finally:
            self._refreshing = False

    def set_autorefresh(self, auto=True):
        self._autorefresh = True
    def get_autorefresh(self):
        return self._autorefresh
    autorefresh = property(get_autorefresh, set_autorefresh,
                           doc="If true, refresh the plot after every call.")

    def repr(self):
        return "<Plot %s>" % _ObservedList.repr()

class SPlot(Plot):
    def __init__(self, command=None, persist=True):
        # When Plot.refresh() calls Gnuplot.plot(), redirect it to splot().
        self.plot = self.splot
        Plot.__init__(self, command, persist)

    def repr(self):
        return "<SPlot %s>" % _ObservedList.repr()

