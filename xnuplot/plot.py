from .gnuplot import Gnuplot

class _ObservedList(list):
    # A list that calls self.refresh() upon modification.
    def refresh(self):
        pass
    def __with_refresh(func):
        def call_and_refresh(self, *args, **kwargs):
            result = func(self, *args, **kwargs)
            self.refresh()
            return result
        return call_and_refresh
    append = __with_refresh(list.append)
    extend = __with_refresh(list.extend)
    insert = __with_refresh(list.insert)
    pop = __with_refresh(list.pop)
    remove = __with_refresh(list.remove)
    reverse = __with_refresh(list.reverse)
    sort = __with_refresh(list.sort)
    __setitem__ = __with_refresh(list.__setitem__)
    __delitem__ = __with_refresh(list.__delitem__)
    __setslice__ = __with_refresh(list.__setslice__)
    __delslice__ = __with_refresh(list.__delslice__)
    __iadd__ = __with_refresh(list.__iadd__)
    __imul__ = __with_refresh(list.__imul__)

class Plot(Gnuplot, _ObservedList):
    _plotmethod = Gnuplot.plot

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
                self._plotmethod(*self)
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

    def __repr__(self):
        classname = self.__class__.__name__
        return "<%s %s>" % (classname, _ObservedList.__repr__(self))

class SPlot(Plot):
    _plotmethod = Gnuplot.splot

