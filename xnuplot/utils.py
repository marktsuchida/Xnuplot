import re
import sys
import contextlib


@contextlib.contextmanager
def no_autorefresh(plot):
    """A `with' statement context manager to switch off autorefresh."""
    if hasattr(plot, "autorefresh"):
        saveautorefresh = plot.autorefresh
        plot.autorefresh = False
    else:
        saveautorefresh = None
    yield plot
    if saveautorefresh is not None:
        plot.autorefresh = saveautorefresh


_getvar_pattern = re.compile("GETVAR_LEFT (.*) GETVAR_RIGHT")
def get_var(plot, varname, type_=str):
    """Get the value of a Gnuplot variable from plot."""
    with no_autorefresh(plot) as plot2:
        result = plot2("print \"GETVAR_LEFT \", %s, \" GETVAR_RIGHT\"" %
                       varname)
    match = _getvar_pattern.search(result)
    if not match:
        return None
    value = match.group(1)
    if value is not None:
        return type_(value)


def convert_coord(plot, axis, to_system, coord):
    """Convert coord from one system to the other.

    The axis ranges are taken from the last plot, not necessarily the current
    settings.

    convert_coord(plot, "x", 2, x1) -> x2
    """
    to_system = int(to_system)
    from_system = 2 - to_system
    from_name = axis.upper() + ("2" if from_system == 2 else "")
    to_name = axis.upper() + ("2" if to_system == 2 else "")
    from_min = get_var(plot, "GPVAL_%s_MIN" % from_name, float)
    from_max = get_var(plot, "GPVAL_%s_MAX" % from_name, float)
    to_min = get_var(plot, "GPVAL_%s_MIN" % to_name, float)
    to_max = get_var(plot, "GPVAL_%s_MAX" % to_name, float)
    if None not in (from_min, from_max, to_min, to_max):
        return to_min + (to_max - to_min) * \
                (coord - from_min) / (from_max - from_min)
    else:
        return None


def _convert_given_coord(plot, axis, to_sys, c1=None, c2=None):
    # Subroutine for convert_coords() below.
    if to_sys is not None:
        given = (c1 is not None, c2 is not None)
        if given == (True, False):
            from_sys = 1
            c = c1
        elif given == (False, True):
            from_sys = 2
            c = c2
        else:
            raise ValueError("exactly one of %s1, %s2 must be given" %
                             (axis, axis))
        if int(to_sys) == from_sys:
            return c
        else:
            return convert_coord(plot, axis, to_sys, c)


_axes_pattern = re.compile("^(x([12]))?(y([12]))?$")
def convert_coords(plot, to_axes, x1=None, y1=None, x2=None, y2=None):
    """Convert coordinates between the first and second systems.

    The axis ranges are taken from the last plot, not necessarily the current
    settings.

    convert_coords(plot, "y2", y1=y1) -> y2
    convert_coords(plot, "x1y2", x1=x1, y1=y1) -> (x1, y2)
    """
    to_x_sys, to_y_sys = _axes_pattern.match(to_axes).group(2, 4)
    to_x = _convert_given_coord(plot, "x", to_x_sys, c1=x1, c2=x2)
    to_y = _convert_given_coord(plot, "y", to_y_sys, c1=y1, c2=y2)
    ret = filter(None, (to_x, to_y))
    if len(ret) == 2:
        return ret
    elif len(ret) == 1:
        return ret[0]


def get_range_settings(plot, axis, system=1):
    with no_autorefresh(plot) as plot2:
        return _get_range_settings(plot, axis, system)

def _get_range_settings(plot, axis, system):
    range_name = axis + ("range" if int(system) == 1 else "2range")
    range_str = plot("show " + range_name)

    pattern = ("set +" + range_name +
               r" +\[ *([^ :]+) *: *([^ :]+) *\] +(no)?reverse")
    match = re.search(pattern, range_str)
    if not match:
        return None
    range_min, range_max = match.group(1), match.group(2)
    range_min = (float(range_min) if range_min != "*" else None)
    range_max = (float(range_max) if range_max != "*" else None)
    setting = (range_min, range_max)
    reversed = match.group(3) != "no"

    if None not in setting:
        # The GPVAL_ vars don't reflect Button-3 zoomed ranges, so use the
        # non-auto ranges if set.
        current = (setting if not reversed else (setting[1], setting[0]))
    else:
        name = axis.upper() + ("2" if int(system) == 2 else "")
        current_min = get_var(plot, "GPVAL_%s_MIN" % name, float)
        current_max = get_var(plot, "GPVAL_%s_MAX" % name, float)
        current = (current_min, current_max)

    return dict(setting=setting, reversed=reversed, current=current)


def set_range(plot, axis, system, range, reverse=False, writeback=None):
    range_name = axis + ("range" if int(system) == 1 else "2range")
    range_min = ("%e" % range[0] if range[0] is not None else "*")
    range_max = ("%e" % range[1] if range[1] is not None else "*")
    reverse = (("reverse" if reverse else "noreverse")
               if reverse is not None else None)
    writeback = (("writeback" if writeback else "nowriteback")
                 if writeback is not None else None)
    plot(" ".join(filter(None, ["set", range_name,
                                "[%s:%s]" % (range_min, range_max),
                                reverse, writeback])))


# TODO Events should probably be instances of their own class, rather than
# just a dict.

def get_last_event(plot):
    with no_autorefresh(plot) as plot2:
        return _get_last_event(plot2)

def _get_last_event(plot):
    event = dict(button=get_var(plot, "MOUSE_BUTTON", int),
                 x1=get_var(plot, "MOUSE_X", float),
                 y1=get_var(plot, "MOUSE_Y", float),
                 x2=get_var(plot, "MOUSE_X2", float),
                 y2=get_var(plot, "MOUSE_Y2", float),
                 shift=bool(get_var(plot, "MOUSE_SHIFT", int)),
                 ctrl=bool(get_var(plot, "MOUSE_CTRL", int)),
                 alt=bool(get_var(plot, "MOUSE_ALT", int)),
                 char=get_var(plot, "MOUSE_CHAR"),
                 ascii=get_var(plot, "MOUSE_KEY", int))
    if event["button"] is None or event["button"] == -1:
        if event["ascii"] == -1:
            event["event_type"] = "abnormal"
        else:
            event["event_type"] = "key"
    else:
        event["event_type"] = "click"
    return event


def wait_for_event(plot, callback=None):
    with no_autorefresh(plot) as plot2:
        return _wait_for_event(plot2, callback)

def _wait_for_event(plot, callback):
    should_continue = True
    while should_continue:
        plot.pause("mouse", "any")
        event = get_last_event(plot)

        should_continue = False
        if callback is not None:
            should_continue = callback(event)
        if event["event_type"] == "abnormal":
            should_continue = False
    return event

_full_axes_pattern = re.compile("^x[12]y[12]$")
def _coord_keys(axes):
    # Return e.g. ("x1", "y2") given "x1y2".
    if not _full_axes_pattern.match(axes):
        raise ValueError("invalid axes specifier: " + axes)
    x_coord, y_coord = axes[:2], axes[2:]
    return (x_coord, y_coord)

def get_line_segment(plot, axes="x1y1"):
    with no_autorefresh(plot) as plot2:
        return _get_line_segment(plot2, axes)

def _get_line_segment(plot, axes):
    x_coord, y_coord = _coord_keys(axes)
    points = []
    def action(event):
        if event["event_type"] == "click" and event["button"] == 1:
            if len(points) == 0:
                points.append((event[x_coord], event[y_coord]))
                plot("set mouse ruler at %f,%f polardistance" %
                     (event["x1"], event["y1"]))
                return True
            elif len(points) == 1:
                points.append((event[x_coord], event[y_coord]))
                return False
        elif event["event_type"] == "key" and event["ascii"] == 27: # Esc.
            if len(points) == 0:
                # Cancel line segment.
                return False
            elif len(points) == 1:
                # Cancel first click.
                points.pop()
                plot("set mouse noruler")
                return True
        return True
    wait_for_event(plot, action)
    plot("set mouse noruler nopolardistance")
    if len(points) < 2:
        return None
    return tuple(points)


def get_polyline(plot, axes="x1y1", vertex_callback=None):
    with no_autorefresh(plot) as plot2:
        return _get_polyline(plot2, axes, vertex_callback)

def _get_polyline(plot, axes, vertex_callback):
    x_coord, y_coord = _coord_keys(axes)
    points = []
    def action(event):
        if event["event_type"] == "click":
            points.append((event[x_coord], event[y_coord]))
            plot("set mouse ruler at %f,%f polardistance" %
                 (event["x1"], event["y1"]))
            if vertex_callback is not None:
                vertex_callback(points)
            if event["button"] == 3:
                return False
            return True
        elif event["event_type"] == "key":
            if event["ascii"] == 27: # Esc.
                if len(points):
                    # Cancel last point.
                    points.pop()
                    if vertex_callback is not None:
                        vertex_callback(points)
                    if len(points):
                        coord = convert_coords(plot, "x1y1",
                                               **{x_coord: points[-1][0],
                                                  y_coord: points[-1][1]})
                        plot("set mouse ruler at %f,%f" % coord)
                    else:
                        plot("set mouse noruler")
                    return True
                else:
                    # Cancel polyline.
                    points[:] = [None] # Marker for cancellation.
                    return False
            elif event["ascii"] == 13: # Return.
                return False
        return True
    event = wait_for_event(plot, action)
    plot("set mouse noruler nopolardistance")
    if len(points) and points[0] is None: # Cancelled.
        return None
    if event["event_type"] == "abnormal":
        return None
    return points


def input_polyline(plot, axes="x1y1", with_="lines", leave_polyline=True,
                   close_polygon=False):
    if not isinstance(plot, list) or not hasattr(plot, "refresh"):
        raise ValueError("plot must be an xnuplot.Plot instance")
    with no_autorefresh(plot) as plot2:
        return _input_polyline(plot2, axes, with_, leave_polyline,
                               close_polygon)

def _input_polyline(plot, axes, with_, leave_polyline, close_polygon):
    x_coord, y_coord = _coord_keys(axes)
    # We need to freeze the plot range so that it doesn't change.
    xrange = get_range_settings(plot, "x", system=x_coord[1])
    yrange = get_range_settings(plot, "y", system=y_coord[1])
    set_range(plot, "x", x_coord[1], xrange["current"])
    set_range(plot, "y", y_coord[1], yrange["current"])
    with_spec = ("with " + with_ if with_ else None)

    showing_polyline = [False]
    plot_options = " ".join(filter(None, ["axes %s%s" % (x_coord, y_coord),
                                          "notitle",
                                          with_spec]))

    def polyline_for_vertices(vertices):
        vertex_data = "\n".join("%e %e" % (x, y) for x, y in vertices)
        new_polyline = ((vertex_data, plot_options) if vertex_data else None)
        return new_polyline

    def vertices_changed(vertices):
        changed = False
        if showing_polyline[0]:
            plot.pop()
            showing_polyline[0] = False
            changed = True
        polyline = polyline_for_vertices(vertices)
        if polyline:
            plot.append(polyline)
            showing_polyline[0] = True
            changed = True
        if changed:
            plot.refresh()

    vertices = get_polyline(plot, axes, vertices_changed)

    changed = False
    if showing_polyline[0] and (close_polygon or not leave_polyline):
        plot.pop()
        changed = True
    if leave_polyline and close_polygon and vertices:
        display_vertices = vertices[:]
        if len(display_vertices) > 1:
            display_vertices.append(display_vertices[0])
        polyline = polyline_for_vertices(display_vertices)
        plot.append(polyline)
        changed = True
    if not leave_polyline:
        # Restore axis range settings.
        set_range(plot, "x", x_coord[1],
                  xrange["setting"], reversed=xrange["reversed"])
        set_range(plot, "y", y_coord[1],
                  yrange["setting"], reversed=yrange["reversed"])
        changed = True
    if changed:
        plot.refresh()

    return vertices

