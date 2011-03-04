from . import numplot
from . import utils
import numpy

def imshow(plot, image, axes=None, cliprect=None, adjust_ranges=True,
           image_min=None, image_max=None, adjust_scale=True,
           adjust_layout=True, title=None):
    with utils.no_autorefresh(plot) as plot2:
        adjust_for_image(plot2, image, axes, cliprect, adjust_ranges,
                         image_min, image_max, adjust_scale, adjust_layout)
        axes_spec = ("axes x%dy%d" % axes if axes is not None else None)
        title_spec = "title '%s'" % title if title is not None else "notitle"
        plot2.append(numplot.array(image[..., numpy.newaxis],
                                   " ".join(filter(None, [axes_spec,
                                                          title_spec,
                                                          "with image"]))))
    if plot.autorefresh:
        plot.refresh()


def adjust_for_image(plot, image, axes=None, cliprect=None, adjust_ranges=True,
                     image_min=None, image_max=None, adjust_scale=True,
                     adjust_layout=True):
    with utils.no_autorefresh(plot) as plot2:
        if adjust_ranges:
            if cliprect:
                top, left, height, width = cliprect
            else:
                top, left, height, width = 0, 0, image.shape[0], image.shape[1]
            top -= 0.5
            left -= 0.5
            bottom = top + height
            right = left + width
            plot2("set size ratio -1")
            if axes:
                x_sys, y_sys = axes
            else:
                x_sys, y_sys = 1, 1
            utils.set_range(plot2, "x", system=x_sys, range=(left, right))
            utils.set_range(plot2, "y", system=y_sys, range=(bottom, top))
        if adjust_scale:
            image_min = str(image_min) if image_min is not None else "*"
            image_max = str(image_max) if image_max is not None else "*"
            plot2("set cbrange [%s:%s]" % (image_min, image_max))
        if adjust_layout:
            plot2("set key outside")
    if plot.autorefresh:
        plot.refresh()

