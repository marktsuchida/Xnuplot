import re
import sys
import contextlib


# TODO Allow using different coordinates for x and y (e.g. x1y2).


@contextlib.contextmanager
def no_autorefresh(plot):
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
    with no_autorefresh(plot) as plot2:
        result = plot2("print \"GETVAR_LEFT \", %s, \" GETVAR_RIGHT\"" %
                       varname)
    match = _getvar_pattern.search(result)
    if not match:
        return None
    value = match.group(1)
    if value is not None:
        return type_(value)


def _scale(plot, coord, axis, from_system):
    to_system = str(2 - int(from_system))
    from_name = axis.upper() + ("2" if int(from_system) == 2 else "")
    to_name = axis.upper() + ("2" if int(to_system) == 2 else "")
    from_min = get_var(plot, "GPVAL_%s_MIN" % from_name, float)
    from_max = get_var(plot, "GPVAL_%s_MAX" % from_name, float)
    to_min = get_var(plot, "GPVAL_%s_MIN" % to_name, float)
    to_max = get_var(plot, "GPVAL_%s_MAX" % to_name, float)
    if None not in (from_min, from_max, to_min, to_max):
        return to_min + (to_max - to_min) * \
                (coord - from_min) / (from_max - from_min)
    else:
        return None


def first_to_second(plot, x1, y1):
    # Convert based on the last plot, not the current settings.
    x2 = _scale(plot, x1, "x", 1)
    y2 = _scale(plot, y1, "y", 1)
    return x2, y2


def second_to_first(plot, x2, y2):
    # Convert based on the last plot, not the current settings.
    x1 = _scale(plot, x2, "x", 2)
    y1 = _scale(plot, y2, "y", 2)
    return x1, y1


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


def get_last_event(plot):
    with no_autorefresh(plot) as plot2:
        return _get_last_event(plot2)

def _get_last_event(plot):
    event = dict(button=get_var(plot, "MOUSE_BUTTON", int),
                 coord1=(get_var(plot, "MOUSE_X", float),
                         get_var(plot, "MOUSE_Y", float)),
                 coord2=(get_var(plot, "MOUSE_X2", float),
                         get_var(plot, "MOUSE_Y2", float)),
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


def get_interactive_event(plot, callback=None):
    with no_autorefresh(plot) as plot2:
        return _get_interactive_event(plot2, callback)

def _get_interactive_event(plot, callback):
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


def get_line_segment(plot, system=1):
    with no_autorefresh(plot) as plot2:
        return _get_line_segment(plot2, system)

def _get_line_segment(plot, system):
    points = []
    def action(event):
        if event["event_type"] == "click" and event["button"] == 1:
            if len(points) == 0:
                points.append(event["coord1" if system == 1 else "coord2"])
                plot("set mouse ruler at %f,%f polardistance" %
                     event["coord1"])
                return True
            elif len(points) == 1:
                points.append(event["coord1" if system == 1 else "coord2"])
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
    get_interactive_event(plot, action)
    plot("set mouse noruler nopolardistance")
    if len(points) < 2:
        return None
    return tuple(points)


def get_polyline(plot, system=1, vertex_callback=None):
    with no_autorefresh(plot) as plot2:
        return _get_polyline(plot2, system, vertex_callback)

def _get_polyline(plot, system, vertex_callback):
    points = []
    def action(event):
        if event["event_type"] == "click":
            points.append(event["coord1" if system == 1 else "coord2"])
            plot("set mouse ruler at %f,%f polardistance" % event["coord1"])
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
                        coord = (points[-1] if system == 1 else
                                 second_to_first(plot, points[-1]))
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
    last_event = get_interactive_event(plot, action)
    plot("set mouse noruler nopolardistance")
    if len(points) and points[0] is None: # Cancelled.
        return None
    if last_event["event_type"] == "abnormal":
        return None
    return points


def input_polyline(plot, system=1, with_="lines", leave_polyline=True,
                   close_polygon=False):
    if not isinstance(plot, list) or not hasattr(plot, "refresh"):
        raise ValueError("plot must be an xnuplot.Plot instance")
    with no_autorefresh(plot) as plot2:
        return _input_polyline(plot2, system, with_, leave_polyline,
                               close_polygon)

def _input_polyline(plot, system, with_, leave_polyline, close_polygon):
    # We need to freeze the plot range so that it doesn't change.
    xrange = get_range_settings(plot, "x", system=system)
    yrange = get_range_settings(plot, "y", system=system)
    set_range(plot, "x", system, xrange["current"])
    set_range(plot, "y", system, yrange["current"])
    with_spec = ("with " + with_ if with_ else None)

    showing_polyline = [False]
    plot_options = " ".join(filter(None, ["axes x%dy%d" % (system, system),
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

    vertices = get_polyline(plot, system, vertices_changed)

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
        set_range(plot, "x", system,
                  xrange["setting"], reversed=xrange["reversed"])
        set_range(plot, "y", system,
                  yrange["setting"], reversed=yrange["reversed"])
        changed = True
    if changed:
        plot.refresh()

    return vertices

